from datetime import datetime

from fastapi import APIRouter, Depends
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
    """从请求消息中取最后一条非空用户文本，供 Agent 与确认校验使用。"""
    if not data.messages:
        raise BusinessException(message="对话内容为空")
    for message in reversed(data.messages):
        if message.role == "user" and message.content and message.content.strip():
            return message.content.strip()
    raise BusinessException(message="请输入您要对话的内容")


@router.post("/chat")
def chat(
    data: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """多轮对话：无 thread 则建会话，落库后调用 Agent（需登录）"""
    last_user_text = _last_user_text(data)
    thread_id = data.thread_id

    if not thread_id:
        session = ai_chat_session_service.create_session(db, current_user)
    else:
        session = ai_chat_session_service.get_owned_by_thread(
            db, current_user, thread_id
        )

    # 先取「本轮之前」历史，再落库 user，避免冷启动重复本轮 Human
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

    ai_chat_session_service.add_message(db, session, "assistant", content, commit=False)
    ai_chat_session_service.touch_session(db, session, commit=True)

    return Response.success(
        data=ChatReply(role="assistant", content=content, thread_id=session.thread_id)
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
