"""实验室知识库：文件路由向量 + ## 小节，embedding 仅标题+正文核心。"""

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

# 向量召回条数（文件锁不上时的兜底）
SEARCH_CANDIDATES = 8
# 低于该余弦相似度的候选丢掉；cosine 距离 ≈ 1 - 相似度
MIN_SIMILARITY = 0.28
# 文件路由向量过线才锁定手册
FILE_MIN_SIMILARITY = 0.36
# 小节向量相对 top1 的保留比例（弱词面命中时用来补同文件相关节）
SECTION_RELATIVE = 0.88
# 小节标题命中长度达到该值则只按词面选节，不再用向量扩节
LEX_STRONG = 4
# 入库格式：文件路由向量 + ## 小节；对不上则整库重建
INDEX_SCHEMA = "v4-file-section"

# 只在二级标题前切开（一级开篇不入库）
_H2_SPLIT = re.compile(r"(?=^##\s+)", re.MULTILINE)
_H1_LINE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_H2_LINE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_DOC_TYPE = re.compile(r"^[^（(]+")
# 「本文只说明」「本条只讲」等元描述整句
_META_SENT = re.compile(
    r"[^。\n]*(?:本文只说明|本条只讲|本条只给|本条只约束)[^。\n]*。?"
)

_collection: Collection | None = None  # 进程内缓存的 lab_kb 集合
_embedding_fn = None  # 进程内缓存的 Embedding 客户端


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
    """返回 Chroma 用的 Embedding 函数（按 .env 的 EMBEDDING_* 创建，进程内只建一次）。"""
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


def _strip_meta(text: str) -> str:
    """去掉「本文只说明」「本条只讲」一类元描述，只留规定正文。"""
    cleaned = _META_SENT.sub("", text or "")
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _doc_type_from_h1(raw: str, fallback: str) -> str:
    """从一级标题取出文档主题（括号前的文字）。

    例如「# 安全规范（着装…）」得到「安全规范」。没有一级标题时用 fallback（一般为文件名）。
    """
    match = _H1_LINE.search(raw or "")
    if not match:
        return fallback
    title = match.group(1).strip()
    typed = _DOC_TYPE.match(title)
    return (typed.group(0).strip() if typed else title) or fallback


def _section_from_h2(heading: str, doc_type: str) -> str:
    """从二级标题取出小节名。

    「安全规范·实验服与护目镜」且前缀等于 doc_type 时只留「实验服与护目镜」；
    没有间隔号、或前缀对不上时返回整段标题。
    """
    heading = (heading or "").strip()
    if "·" in heading:
        left, right = heading.split("·", 1)
        if left.strip() == doc_type:
            return right.strip() or heading
        return heading
    return heading


def _load_chunks() -> tuple[list[str], list[str], list[dict]]:
    """扫描 data/kb/*.md，生成可交给 Chroma add() 的 (ids, documents, metadatas)。

    每个 md 先写一条 level=file：document 为「主题 + 顿号连接的各节标题」，用于宽问锁手册。
    再为每个 ## 写一条 level=section：document 为「主题·小节 + 去掉元描述后的正文」。
    id 形如 预约规则#file、预约规则#0。
    """
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []
    for path in sorted(KB_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            continue
        doc_type = _doc_type_from_h1(raw, path.stem)
        parts = [p.strip() for p in _H2_SPLIT.split(raw) if p.strip().startswith("##")]
        sections: list[tuple[str, str]] = []
        for part in parts:
            heading_match = _H2_LINE.search(part)
            heading = heading_match.group(1).strip() if heading_match else ""
            section = _section_from_h2(heading, doc_type)
            body = _strip_meta(_H2_LINE.sub("", part, count=1))
            if not body:
                continue
            sections.append((section, body))
        if not sections:
            continue
        section_count = len(sections)
        # 文件路由向量：只含手册名和各节标题，不把开篇元描述写进 embedding
        ids.append(f"{path.stem}#file")
        docs.append(f"{doc_type}\n" + "、".join(s for s, _ in sections))
        metas.append(
            {
                "level": "file",
                "source": path.name,
                "doc_type": doc_type,
                "section": "",
                "chunk": -1,
                "section_count": section_count,
            }
        )
        for index, (section, body) in enumerate(sections):
            ids.append(f"{path.stem}#{index}")
            docs.append(f"{doc_type}·{section}\n{body}")
            metas.append(
                {
                    "level": "section",
                    "source": path.name,
                    "doc_type": doc_type,
                    "section": section,
                    "chunk": index,
                    "section_count": section_count,
                }
            )
    return ids, docs, metas


def _needs_rebuild(col: Collection, fingerprint: str) -> bool:
    """判断现有集合是否要删掉重建。

    空集合、距离空间不是 cosine、入库格式版本不一致、或 md 指纹与入库时不一致，都需要重建。
    """
    meta = col.metadata or {}
    if col.count() == 0:
        return True
    if meta.get("hnsw:space") != "cosine":
        return True
    if meta.get("kb_schema") != INDEX_SCHEMA:
        return True
    if meta.get("kb_fingerprint") != fingerprint:
        return True
    return False


def get_collection() -> Collection:
    """返回可用的 lab_kb 集合（进程内缓存）。

    集合不存在、为空、距离不是 cosine、kb_schema 或 md 指纹与当前不一致时，删除后按 _load_chunks 重建。
    """
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
        metadata={
            "hnsw:space": "cosine",
            "kb_fingerprint": fingerprint,
            "kb_schema": INDEX_SCHEMA,
        },
    )
    ids, docs, metas = _load_chunks()
    if docs:
        col.add(ids=ids, documents=docs, metadatas=metas)
        sources = {m["source"] for m in metas}
        logger.info(
            "向量库入库完成：%s 个切片 / %s 个 md（含文件路由向量）",
            len(docs),
            len(sources),
        )
    else:
        logger.warning("知识库目录没有可入库的 md：%s", KB_DIR)

    _collection = col
    return col


def _similarity(distance: float) -> float:
    """把 Chroma cosine 距离转成 [0, 1] 相似度（约等于 1 - distance）。"""
    return max(0.0, min(1.0, 1.0 - float(distance)))


def _unpack_query(res: dict) -> list[dict]:
    """把 Chroma query 的 documents/metadatas/distances 收成带 score 的命中列表。"""
    docs = (res.get("documents") or [[]])[0]
    metadatas = (res.get("metadatas") or [[]])[0]
    distances = (res.get("distances") or [[]])[0]
    rows: list[dict] = []
    for doc, meta, dist in zip(docs, metadatas, distances):
        if not doc:
            continue
        meta = meta or {}
        rows.append(
            {
                "score": _similarity(dist),
                "source": meta.get("source") or "",
                "doc_type": meta.get("doc_type") or "",
                "section": meta.get("section") or "",
                "chunk": int(meta.get("chunk") or 0),
                "level": meta.get("level") or "",
                "content": doc,
            }
        )
    return rows


def _format_sections(source: str, rows: list[dict]) -> str:
    """把同一 md 的小节按 chunk 顺序拼成给 Agent 的文本，开头带 [文件名]。"""
    ordered = sorted(rows, key=lambda x: x["chunk"])
    body = "\n\n".join(item["content"] for item in ordered)
    return f"[{source or '知识库'}]\n{body}"


def _section_lexical(query: str, section: str) -> int:
    """计算问句与小节标题的最长字面命中长度，用于判断问的是哪一节。

    会用完整标题、去掉「实验室」的前缀、以及 2～6 字片段去匹配；
    标题含「占用」且问句像「占不占」时额外记一次占用命中。未命中返回 0。
    """
    if not query or not section:
        return 0
    needles = [section]
    if section.endswith("实验室") and len(section) > 3:
        needles.append(section[: -len("实验室")])
    max_n = min(6, len(section))
    for n in range(2, max_n + 1):
        for i in range(0, len(section) - n + 1):
            gram = section[i : i + n]
            if gram != "实验室":
                needles.append(gram)
    if "占用" in section and ("占用" in query or "占不占" in query or "占实验室" in query):
        needles.append("占用")
    best = 0
    for token in needles:
        if token in query:
            best = max(best, len(token))
    return best


def _list_file_docs(col: Collection) -> list[dict]:
    """取出集合里全部 level=file 记录的 source 与 doc_type，供标题路由使用。"""
    got = col.get(where={"level": "file"}, include=["metadatas"])
    rows: list[dict] = []
    for meta in got.get("metadatas") or []:
        if not meta:
            continue
        rows.append(
            {
                "source": meta.get("source") or "",
                "doc_type": meta.get("doc_type") or "",
            }
        )
    return rows


def _route_source(col: Collection, query: str) -> str | None:
    """锁定问句对应的 md 文件名。

    问句里唯一（或最长词更长）命中某个 doc_type 则直接用该文件；
    多份打平或标题对不上时，用 level=file 向量取过 FILE_MIN_SIMILARITY 的 top1。
    仍没有则返回 None，由 search 再走小节向量兜底。
    """
    files = _list_file_docs(col)
    if not files:
        return None
    typed = []
    for item in files:
        doc_type = item["doc_type"]
        if doc_type and doc_type in query:
            typed.append((len(doc_type), item["source"]))
    if typed:
        typed.sort(key=lambda x: x[0], reverse=True)
        # 最长 doc_type 唯一领先才用标题锁定，避免「预约」这类词同时命中多份
        if len(typed) == 1 or typed[0][0] > typed[1][0]:
            logger.info("kb 文件路由 via=title source=%s", typed[0][1])
            return typed[0][1]

    limit = min(len(files), 8)
    res = col.query(query_texts=[query], n_results=limit, where={"level": "file"})
    ranked = [row for row in _unpack_query(res) if row["score"] >= FILE_MIN_SIMILARITY]
    ranked.sort(key=lambda x: x["score"], reverse=True)
    if not ranked:
        return None
    logger.info(
        "kb 文件路由 via=vector source=%s score=%.3f",
        ranked[0]["source"],
        ranked[0]["score"],
    )
    return ranked[0]["source"] or None


def _sections_of(col: Collection, source: str) -> list[dict]:
    """取出指定 md 的全部 level=section 切片，按 chunk 升序，score 先置 0。"""
    got = col.get(
        where={"$and": [{"level": "section"}, {"source": source}]},
        include=["documents", "metadatas"],
    )
    rows: list[dict] = []
    for doc, meta in zip(got.get("documents") or [], got.get("metadatas") or []):
        if not doc:
            continue
        meta = meta or {}
        rows.append(
            {
                "score": 0.0,
                "source": meta.get("source") or source,
                "doc_type": meta.get("doc_type") or "",
                "section": meta.get("section") or "",
                "chunk": int(meta.get("chunk") or 0),
                "level": "section",
                "content": doc,
            }
        )
    rows.sort(key=lambda x: x["chunk"])
    return rows


def _attach_section_scores(col: Collection, query: str, source: str, rows: list[dict]) -> None:
    """在该 md 的小节子集上做向量检索，把相似度写回 rows 的 score（按 chunk 对齐）。"""
    if not rows:
        return
    res = col.query(
        query_texts=[query],
        n_results=len(rows),
        where={"$and": [{"level": "section"}, {"source": source}]},
    )
    by_chunk = {row["chunk"]: row for row in rows}
    for hit in _unpack_query(res):
        item = by_chunk.get(hit["chunk"])
        if item is not None:
            item["score"] = hit["score"]


def _pick_sections(query: str, rows: list[dict]) -> list[dict]:
    """在已锁定的文件内挑选要返回的小节。

    小节标题都对不上问句：视为宽问，返回该文件全部小节。
    标题命中达到 LEX_STRONG：只留词面相对最高的那些节。
    命中较弱：再并入向量分接近 top1 的同文件小节（如显微镜问占用）。
    """
    if not rows:
        return []
    lex = [( _section_lexical(query, row["section"]), row) for row in rows]
    max_lex = max(score for score, _ in lex)
    if max_lex <= 0:
        # 只命中手册名、对不上任何 ##：返回该文件全部小节
        return rows

    kept: dict[int, dict] = {}
    for score, row in lex:
        if score > 0 and score >= max_lex * 0.85:
            kept[row["chunk"]] = row

    # 词面不够强时（如「显微镜」只有 3 字）再用向量把占用等相邻节补进来
    if max_lex < LEX_STRONG:
        top_vec = max((row["score"] for row in rows), default=0.0)
        if top_vec >= MIN_SIMILARITY:
            for row in rows:
                if row["score"] >= top_vec * SECTION_RELATIVE:
                    kept[row["chunk"]] = row

    if not kept:
        return rows
    return sorted(kept.values(), key=lambda x: x["chunk"])


def search(query: str) -> str:
    """先用文件向量/标题锁定 md，再在该文件小节里决定全文或若干节。

    宽问（只命中手册名）返回该文件全部小节；窄问返回命中的小节。
    文件锁不上时用小节向量 top1 的 source 再走同样逻辑。未命中返回空字符串。
    """
    q = (query or "").strip()
    if not q:
        return ""
    col = get_collection()
    if col.count() == 0:
        logger.warning("向量库为空，无法检索")
        return ""

    source = _route_source(col, q)
    if not source:
        # 标题和文件向量都锁不上：用小节近邻的 top1 文件再走选节
        limit = min(SEARCH_CANDIDATES, col.count())
        fallback = [
            row
            for row in _unpack_query(
                col.query(
                    query_texts=[q],
                    n_results=limit,
                    where={"level": "section"},
                )
            )
            if row["score"] >= MIN_SIMILARITY
        ]
        fallback.sort(key=lambda x: x["score"], reverse=True)
        if not fallback:
            return ""
        source = fallback[0]["source"]
        logger.info("kb 文件路由 via=section-fallback source=%s", source)

    rows = _sections_of(col, source)
    if not rows:
        return ""
    _attach_section_scores(col, q, source, rows)
    picked = _pick_sections(q, rows)
    logger.info(
        "kb 命中 source=%s sections=%s",
        source,
        [item["section"] for item in picked],
    )
    return _format_sections(source, picked)


def warmup() -> None:
    """启动时加载 embedding、必要时重建索引，并打一次 query，避免首个用户问题卡住。"""
    col = get_collection()
    if col.count() > 0:
        col.query(query_texts=["实验室预约规则"], n_results=1)
        logger.info("向量库预热完成，切片数=%s", col.count())
    else:
        logger.warning("向量库预热完成但集合为空，请检查 data/kb 与 EMBEDDING_BASE_URL")
