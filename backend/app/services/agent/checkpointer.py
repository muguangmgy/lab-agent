"""LangGraph RedisSaver 单例：lifespan 初始化，勿在 import 时连接 Redis。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.common.exceptions import BusinessException

if TYPE_CHECKING:
    from langgraph.checkpoint.redis import RedisSaver

logger = logging.getLogger("uvicorn.error")

_checkpointer: RedisSaver | None = None


def init_checkpointer(redis_url: str) -> RedisSaver:
    """创建 RedisSaver 并 setup（同步；由 lifespan 用 to_thread 调用）。失败即 raise。"""
    global _checkpointer
    from langgraph.checkpoint.redis import RedisSaver

    saver = RedisSaver(redis_url=redis_url)
    saver.setup()
    _checkpointer = saver
    logger.info("Redis checkpointer 初始化成功")
    return saver


def get_checkpointer() -> RedisSaver:
    """返回已初始化的 RedisSaver；未就绪则业务异常。"""
    if _checkpointer is None:
        raise BusinessException(message="对话服务暂不可用，请稍后重试")
    return _checkpointer


def delete_thread(thread_id: str) -> None:
    """删除指定 thread 的 Redis checkpoint；无 API / 失败时吞掉，不阻断软删。"""
    if not thread_id or _checkpointer is None:
        return
    try:
        _checkpointer.delete_thread(thread_id)
    except Exception:
        logger.exception("清理 Redis checkpoint 失败 thread_id=%s", thread_id)


def close_checkpointer() -> None:
    """关闭 Redis 连接（lifespan finally）。"""
    global _checkpointer
    if _checkpointer is None:
        return
    try:
        client = getattr(_checkpointer, "_redis", None)
        if client is not None:
            client.close()
            pool = getattr(client, "connection_pool", None)
            if pool is not None:
                pool.disconnect()
    except Exception:
        logger.exception("关闭 Redis checkpointer 连接失败")
    finally:
        _checkpointer = None
