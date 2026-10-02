"""AI 聊天会话：MySQL 侧栏列表 / 气泡；归属校验；写操作显式 commit。"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.models.ai_chat import (
    DEFAULT_SESSION_TITLE,
    AiChatMessage,
    AiChatSession,
)
from app.models.user import User
from app.services.agent import checkpointer as agent_checkpointer

# 冷启动回填最多取最近 N 条（不含本轮）
COLD_START_MESSAGE_LIMIT = 40


def create_session(db: Session, user: User, title: str | None = None) -> AiChatSession:
    """新建会话（生成 thread_id，默认标题）"""
    session = AiChatSession(
        thread_id=str(uuid4()),
        user_id=user.id,
        title=(title or DEFAULT_SESSION_TITLE).strip() or DEFAULT_SESSION_TITLE,
        is_deleted=False,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_sessions(db: Session, user: User) -> list[AiChatSession]:
    """列出本人未软删会话，按更新时间倒序"""
    return (
        db.query(AiChatSession)
        .filter(AiChatSession.user_id == user.id, AiChatSession.is_deleted.is_(False))
        .order_by(AiChatSession.update_time.desc())
        .all()
    )


def get_owned_by_thread(
    db: Session, user: User, thread_id: str, *, allow_deleted: bool = False
) -> AiChatSession:
    """按 thread_id 取本人会话；不存在与非本人统一 403。"""
    if not thread_id or not str(thread_id).strip():
        raise BusinessException(message="无权限访问", code=403)
    session = (
        db.query(AiChatSession)
        .filter(AiChatSession.thread_id == thread_id.strip())
        .first()
    )
    if not session or session.user_id != user.id:
        raise BusinessException(message="无权限访问", code=403)
    if session.is_deleted and not allow_deleted:
        raise BusinessException(message="无权限访问", code=403)
    return session


def soft_delete(db: Session, user: User, thread_id: str) -> None:
    """软删本人会话，并尽力清理 Redis checkpoint"""
    session = get_owned_by_thread(db, user, thread_id)
    session.is_deleted = True
    session.update_time = datetime.now()
    db.commit()
    agent_checkpointer.delete_thread(session.thread_id)


def update_title(db: Session, user: User, thread_id: str, title: str) -> AiChatSession:
    """更新本人会话标题（最长 100 字）"""
    session = get_owned_by_thread(db, user, thread_id)
    cleaned = (title or "").strip()
    if not cleaned:
        raise BusinessException(message="标题不能为空")
    session.title = cleaned[:100]
    session.update_time = datetime.now()
    db.commit()
    db.refresh(session)
    return session


def touch_session(
    db: Session,
    session: AiChatSession,
    *,
    title_from_user: str | None = None,
    commit: bool = True,
) -> None:
    """显式更新 update_time；仅默认标题时用首条 user 截断覆盖。"""
    session.update_time = datetime.now()
    if (
        title_from_user
        and session.title == DEFAULT_SESSION_TITLE
        and title_from_user.strip()
    ):
        session.title = title_from_user.strip()[:20]
    if commit:
        db.commit()
        db.refresh(session)


def add_message(
    db: Session,
    session: AiChatSession,
    role: str,
    content: str,
    *,
    commit: bool = True,
) -> AiChatMessage:
    """写入一条会话消息；可延迟 commit 以便与 touch 同事务。"""
    msg = AiChatMessage(
        session_id=session.id,
        role=role,
        content=content,
    )
    db.add(msg)
    if commit:
        db.commit()
        db.refresh(msg)
    return msg


def list_messages(
    db: Session,
    session: AiChatSession,
    *,
    limit: int | None = None,
) -> list[AiChatMessage]:
    """按 id 升序取会话消息；limit 时取最近 N 条仍升序返回。"""
    query = (
        db.query(AiChatMessage)
        .filter(AiChatMessage.session_id == session.id)
        .order_by(AiChatMessage.id.asc())
    )
    if limit is not None and limit > 0:
        # 取最近 N 条，仍按 id 升序返回
        total = query.count()
        if total > limit:
            offset = total - limit
            return query.offset(offset).limit(limit).all()
    return query.all()
