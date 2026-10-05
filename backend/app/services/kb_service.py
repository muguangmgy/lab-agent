"""实验室知识库：Markdown 切块入库 + Chroma 余弦检索。"""

from __future__ import annotations

import hashlib
import logging
import re

from chromadb.api.models.Collection import Collection
from chromadb.utils import embedding_functions
import chromadb

from app.config import resolve_data_path, settings

logger = logging.getLogger("uvicorn.error")

KB_DIR = resolve_data_path(settings.KB_DIR)
CHROMA_DIR = resolve_data_path(settings.CHROMA_DIR)
COLLECTION_NAME = "lab_kb"

# 单块最大字符数；超出才按长度再切
CHUNK_MAX_CHARS = 700
# 长度切块时与上一块重叠的字符数，减轻句子被切断
CHUNK_OVERLAP = 80
# 向量召回条数（先多捞）
SEARCH_CANDIDATES = 8
# 实际拼给 Agent 的条数（再精选）
SEARCH_RETURN = 4
# 低于该余弦相似度的候选丢掉；cosine 距离 ≈ 1 - 相似度
MIN_SIMILARITY = 0.28

# 在 # / ## / ### 标题前切开，标题本身留在下一块开头
_HEADING_SPLIT = re.compile(r"(?=^#{1,3}\s)", re.MULTILINE)

_collection: Collection | None = None
_embedding_fn = None


def _normalize_embedding_base_url(url: str) -> str:
    """规范化 Embedding 的 API 根地址。

    OpenAI 兼容客户端会自己拼接 /embeddings，base 应停在 /v1。
    若配置误写成完整 embeddings URL，去掉末尾路径并告警。
    """
    raw = (url or "").strip().rstrip("/")
    if raw.endswith("/embeddings"):
        raw = raw[: -len("/embeddings")].rstrip("/")
        logger.warning(
            "EMBEDDING_BASE_URL 含 /embeddings，已纠正为 %s（客户端会自动追加该路径）",
            raw,
        )
    return raw


def get_embedding_fn():
    """返回 Chroma 使用的 Embedding 函数（懒加载，进程内只创建一次）。"""
    global _embedding_fn
    if _embedding_fn is not None:
        return _embedding_fn
    _embedding_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_key=settings.EMBEDDING_API_KEY,
        api_base=_normalize_embedding_base_url(settings.EMBEDDING_BASE_URL),
        model_name=settings.EMBEDDING_MODEL,
    )
    return _embedding_fn


def _kb_fingerprint() -> str:
    """根据 kb 目录下全部 md 的文件名+内容生成短指纹。

    任一文件增删改都会变化，用来判断 Chroma 集合是否过期、要不要整库重建。
    """
    hasher = hashlib.sha256()
    files = sorted(KB_DIR.glob("*.md"))
    if not files:
        hasher.update(b"empty")
        return hasher.hexdigest()[:16]
    for path in files:
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()[:16]


def _split_by_length(text: str) -> list[str]:
    """把超长文本按 CHUNK_MAX_CHARS 切开，优先在换行处断开，块之间保留重叠。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= CHUNK_MAX_CHARS:
        return [text]
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + CHUNK_MAX_CHARS, n)
        piece = text[start:end]
        if end < n:
            nl = piece.rfind("\n")
            if nl >= CHUNK_MAX_CHARS // 2:
                end = start + nl
                piece = text[start:end]
        piece = piece.strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def _split_markdown(text: str) -> list[str]:
    """按 Markdown 一到三级标题切块；单块仍超长时再交给 _split_by_length。"""
    text = (text or "").strip()
    if not text:
        return []
    headings = [p.strip() for p in _HEADING_SPLIT.split(text) if p.strip()]
    parts = headings or [text]
    chunks: list[str] = []
    for part in parts:
        chunks.extend(_split_by_length(part))
    return chunks


def _load_chunks() -> tuple[list[str], list[str], list[dict]]:
    """读取 data/kb/*.md 并切块。

    返回 (ids, documents, metadatas)，与 Chroma add() 对齐。
    每条 document 前会加上「来源：文件名」，id 形如 预约规则#0。
    """
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []
    for path in sorted(KB_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            continue
        pieces = _split_markdown(raw)
        for index, piece in enumerate(pieces):
            body = f"来源：{path.name}\n{piece}"
            ids.append(f"{path.stem}#{index}")
            docs.append(body)
            metas.append(
                {
                    "source": path.name,
                    "chunk": index,
                    "title": path.stem,
                }
            )
    return ids, docs, metas


def _needs_rebuild(col: Collection, fingerprint: str) -> bool:
    """判断现有集合是否要删掉重建。

    空集合、距离空间不是 cosine、或 md 指纹与入库时不一致，都需要重建。
    """
    meta = col.metadata or {}
    if col.count() == 0:
        return True
    if meta.get("hnsw:space") != "cosine":
        return True
    if meta.get("kb_fingerprint") != fingerprint:
        return True
    return False


def get_collection() -> Collection:
    """拿到可用的 lab_kb 集合；进程内缓存，必要时按当前 md 整库重建。"""
    global _collection
    if _collection is not None:
        return _collection

    KB_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    fingerprint = _kb_fingerprint()
    embedding_fn = get_embedding_fn()

    existing: Collection | None = None
    try:
        existing = client.get_collection(
            name=COLLECTION_NAME, embedding_function=embedding_fn
        )
    except Exception:
        existing = None

    if existing is not None and not _needs_rebuild(existing, fingerprint):
        _collection = existing
        logger.info("向量库已就绪：%s 条切片", existing.count())
        return _collection

    if existing is not None:
        client.delete_collection(COLLECTION_NAME)
        logger.info("向量库过期或配置不当，已删除旧集合 lab_kb")

    col = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine", "kb_fingerprint": fingerprint},
    )
    ids, docs, metas = _load_chunks()
    if docs:
        col.add(ids=ids, documents=docs, metadatas=metas)
        sources = {m["source"] for m in metas}
        logger.info("向量库入库完成：%s 个切片 / %s 个 md", len(docs), len(sources))
    else:
        logger.warning("知识库目录没有可入库的 md：%s", KB_DIR)

    _collection = col
    return col


def _similarity(distance: float) -> float:
    """把 Chroma cosine 距离转成 [0, 1] 相似度（约等于 1 - distance）。"""
    return max(0.0, min(1.0, 1.0 - float(distance)))


def search(query: str) -> str:
    """按用户问题做向量检索，返回拼给 Agent 的文本。

    流程：问题 embedding → 召回最多 SEARCH_CANDIDATES 条 → 过滤低相似度与重复
    → 按分数取 SEARCH_RETURN 条 → 用 --- 拼接。未命中返回空字符串。
    """
    q = (query or "").strip()
    if not q:
        return ""
    col = get_collection()
    total = col.count()
    if total == 0:
        logger.warning("向量库为空，无法检索")
        return ""

    limit = min(SEARCH_CANDIDATES, total)
    res = col.query(query_texts=[q], n_results=limit)
    docs = (res.get("documents") or [[]])[0]
    metadatas = (res.get("metadatas") or [[]])[0]
    distances = (res.get("distances") or [[]])[0]

    scored: list[dict] = []
    seen: set[str] = set()
    for doc, meta, dist in zip(docs, metadatas, distances):
        if not doc:
            continue
        score = _similarity(dist)
        if score < MIN_SIMILARITY:
            continue
        source = (meta or {}).get("source") or ""
        key = f"{source}\n{doc}"
        if key in seen:
            continue
        seen.add(key)
        scored.append({"score": score, "source": source, "content": doc})

    scored.sort(key=lambda x: x["score"], reverse=True)
    picked = scored[:SEARCH_RETURN]
    if not picked:
        return ""

    parts = [f"[{item['source'] or '知识库'}]\n{item['content']}" for item in picked]
    return "\n\n---\n\n".join(parts)


def warmup() -> None:
    """启动时预热：加载 embedding、按需重建索引，并跑一次检索避免首问超时。"""
    col = get_collection()
    if col.count() > 0:
        col.query(query_texts=["实验室预约规则"], n_results=1)
        logger.info("向量库预热完成，切片数=%s", col.count())
    else:
        logger.warning("向量库预热完成但集合为空，请检查 data/kb 与 EMBEDDING_BASE_URL")
