"""AI 聊天会话与消息（侧栏历史在 MySQL；Agent checkpoint 在 Redis）。"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

DEFAULT_SESSION_TITLE = "新对话"


class AiChatSession(Base):
    __tablename__ = "ai_chat_sessions"
    __table_args__ = {"comment": "AI 聊天会话"}

    thread_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True, comment="LangGraph thread_id"
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True, comment="归属用户"
    )
    title: Mapped[str] = mapped_column(
        String(100), nullable=False, default=DEFAULT_SESSION_TITLE, comment="会话标题"
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="软删"
    )

    messages: Mapped[list[AiChatMessage]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class AiChatMessage(Base):
    __tablename__ = "ai_chat_messages"
    __table_args__ = {"comment": "AI 聊天消息（仅 user/assistant 文本）"}

    session_id: Mapped[int] = mapped_column(
        ForeignKey("ai_chat_sessions.id"),
        nullable=False,
        index=True,
        comment="所属会话",
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, comment="user/assistant")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息正文")

    session: Mapped[AiChatSession] = relationship(back_populates="messages")
