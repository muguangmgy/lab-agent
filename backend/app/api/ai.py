import json
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.common.response import Response
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.ai import (
    ChatMessage,
    ChatReply,
    ChatRequest,
    SessionCreateRequest,
    SessionItem,
    SessionUpdateRequest,
)
from app.services.agent import service as agent_service
from app.services.agent import session_service as ai_chat_session_service

router = APIRouter(prefix="/ai", tags=["AI相关的API"])


def _fmt_dt(value: datetime | None) -> str | None:
    """将 datetime 格式化为接口统一时间字符串。"""
    if value is None:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _session_item(session) -> SessionItem:
    """把 ORM 会话转为侧栏列表项 DTO。"""
    return SessionItem(
        thread_id=session.thread_id,
        title=session.title,
        create_time=_fmt_dt(session.create_time),
        update_time=_fmt_dt(session.update_time),
    )


def _last_user_text(data: ChatRequest) -> str:
    """从 ChatRequest 取最后一条非空 user，供 /chat、/chat/stream 与预约确认工具使用。"""
    if not data.messages:
        raise BusinessException(message="对话内容为空")
    for message in reversed(data.messages):
        if message.role == "user" and message.content and message.content.strip():
            return message.content.strip()
    raise BusinessException(message="请输入您要对话的内容")


def _prepare_chat_turn(db: Session, current_user: User, data: ChatRequest):
    """/chat 与 /chat/stream 共用：校验归属、冷启动先取 prior，再 commit 本轮 user。

    顺序不能颠倒：prior 必须在写入本轮 user 之前取出，否则冷启动会把刚写入的 Human 再塞一遍。
    失败时抛 BusinessException（尚未进入 SSE），由全局处理器返回 JSON Response。
    """
    last_user_text = _last_user_text(data)
    thread_id = data.thread_id

    if not thread_id:
        session = ai_chat_session_service.create_session(db, current_user)
    else:
        session = ai_chat_session_service.get_owned_by_thread(
            db, current_user, thread_id
        )

    prior = ai_chat_session_service.list_messages(
        db,
        session,
        limit=ai_chat_session_service.COLD_START_MESSAGE_LIMIT,
    )
    ai_chat_session_service.add_message(
        db, session, "user", last_user_text, commit=False
    )
    ai_chat_session_service.touch_session(
        db, session, title_from_user=last_user_text, commit=True
    )
    return session, last_user_text, prior


def event_frame(event: str, data: dict) -> bytes:
    """拼一帧 SSE：`event:` + 单行 JSON `data:` + 空行，供 StreamingResponse yield。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode(
        "utf-8"
    )


def _to_sse_error(exc: Exception) -> tuple[str, int]:
    """流已经开始后的错误：转成 (message, code)，只发 event:error，不再包 Response JSON。"""
    mapped = agent_service.map_agent_exception(exc)
    return mapped.message, int(mapped.code or 500)


def _commit_assistant(db: Session, session, content: str) -> None:
    """流成功结束（或降级成功）后写入完整 assistant，并刷新会话时间。"""
    ai_chat_session_service.add_message(db, session, "assistant", content, commit=False)
    ai_chat_session_service.touch_session(db, session, commit=True)


def chat_stream_generator(
    db: Session,
    current_user: User,
    session,
    last_user_text: str,
    prior,
):
    """SSE 生成器：meta → 多个 delta → 恰好一个 done 或 error。

    - 增量只在内存拼接；MySQL assistant 仅在成功路径写入（中断半截默认不落库）。
    - 尚未吐出任何 delta 就失败：同连接 run_agent/invoke 降级，禁止前端再打 /chat（user 已 commit）。
    - 已有 delta 后失败：只发 error，保留前端残局。
    """
    yield event_frame("meta", {"thread_id": session.thread_id})
    full: list[str] = []
    emitted_delta = False
    try:
        for piece in agent_service.stream_agent(
            db,
            current_user,
            thread_id=session.thread_id,
            last_user_text=last_user_text,
            prior_messages=prior,
        ):
            if not piece:
                continue
            emitted_delta = True
            full.append(piece)
            yield event_frame("delta", {"content": piece})
        content = "".join(full).strip()
        if not content:
            raise BusinessException(message="大模型没有任何返回内容")
        _commit_assistant(db, session, content)
        yield event_frame(
            "done",
            {
                "role": "assistant",
                "content": content,
                "thread_id": session.thread_id,
            },
        )
    except Exception as exc:
        if not emitted_delta:
            # 首 token 前失败：同连接降级；checkpoint 里可能已有本轮 Human
            try:
                content = agent_service.run_agent(
                    db,
                    current_user,
                    thread_id=session.thread_id,
                    last_user_text=last_user_text,
                    prior_messages=prior,
                    resume_without_duplicate_human=True,
                )
                content = (content or "").strip()
                if not content:
                    raise BusinessException(message="大模型没有任何返回内容")
                yield event_frame("delta", {"content": content})
                _commit_assistant(db, session, content)
                yield event_frame(
                    "done",
                    {
                        "role": "assistant",
                        "content": content,
                        "thread_id": session.thread_id,
                    },
                )
                return
            except Exception as fallback_exc:
                exc = fallback_exc
        msg, code = _to_sse_error(exc)
        yield event_frame("error", {"code": code, "message": msg})


@router.post("/chat")
def chat(
    data: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """非流式多轮对话（兼容保留）。落库顺序与 /chat/stream 相同，Agent 走 invoke 一次返回。"""
    session, last_user_text, prior = _prepare_chat_turn(db, current_user, data)

    try:
        content = agent_service.run_agent(
            db,
            current_user,
            thread_id=session.thread_id,
            last_user_text=last_user_text,
            prior_messages=prior,
        )
    except BusinessException:
        raise
    except Exception:
        raise BusinessException(message="大模型调用失败，请稍后重试")

    _commit_assistant(db, session, content)

    return Response.success(
        data=ChatReply(role="assistant", content=content, thread_id=session.thread_id)
    )


@router.post("/chat/stream")
def chat_stream(
    data: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """SSE 流式对话（请求体复用 ChatRequest）。

    进入 StreamingResponse 之前的失败（鉴权、空消息、403）仍是 HTTP 200 + JSON error。
    进入流之后只推 text/event-stream 事件。前端须用 fetch 读流，不要走 axios。
    """
    session, last_user_text, prior = _prepare_chat_turn(db, current_user, data)
    return StreamingResponse(
        chat_stream_generator(
            db, current_user, session, last_user_text, prior
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions")
def get_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出当前用户未软删的会话（需登录）"""
    sessions = ai_chat_session_service.list_sessions(db, current_user)
    return Response.success(data=[_session_item(s) for s in sessions])


@router.post("/sessions")
def create_session(
    data: SessionCreateRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """新建 AI 会话（需登录）"""
    title = data.title if data else None
    session = ai_chat_session_service.create_session(db, current_user, title=title)
    return Response.success(data=_session_item(session))


@router.get("/sessions/{thread_id}/messages")
def get_session_messages(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """拉取本人会话的历史消息气泡（需登录）"""
    session = ai_chat_session_service.get_owned_by_thread(db, current_user, thread_id)
    messages = ai_chat_session_service.list_messages(db, session)
    return Response.success(
        data=[
            ChatMessage(role=m.role, content=m.content).model_dump() for m in messages
        ]
    )


@router.delete("/sessions/{thread_id}")
def delete_session(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """软删本人会话并尽力清理 Redis checkpoint（需登录）"""
    ai_chat_session_service.soft_delete(db, current_user, thread_id)
    return Response.success(message="删除成功")


@router.patch("/sessions/{thread_id}")
def patch_session(
    thread_id: str,
    data: SessionUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """重命名本人会话标题（需登录）"""
    session = ai_chat_session_service.update_title(
        db, current_user, thread_id, data.title
    )
    return Response.success(data=_session_item(session))
