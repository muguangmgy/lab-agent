import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.api import api
from app.common.exceptions import (
    BusinessException,
    business_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    global_exception_handler,
)

from fastapi.staticfiles import StaticFiles
from app.config import UPLOAD_DIR, settings
from app.services import kb_service, reservation_service
from app.services.agent import checkpointer as agent_checkpointer
from app.services.rbac_seed import seed_rbac

# 显式 import 全部模型，保证 create_all 建出 roles/menus/关联表
import app.models  # noqa: F401

logger = logging.getLogger("uvicorn.error")

Base.metadata.create_all(bind=engine)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时播种 RBAC/预热向量库/初始化 Redis，并跑预约过期扫描。"""
    # 幂等写入角色/菜单/绑定，保证学生可进 lab-equipment 等隐藏路由
    try:
        await asyncio.to_thread(seed_rbac)
    except Exception:
        logger.exception("RBAC 种子写入失败，服务继续启动")
    # 预热向量库：模型加载（约 15s）挪到启动阶段，避免首个请求超过前端 30s 超时
    try:
        await asyncio.to_thread(kb_service.warmup)
    except Exception:
        logger.exception("向量库预热失败，服务继续启动")
    # Redis Checkpointer：连不上 / setup 失败则阻止启动（勿静默降级）
    await asyncio.to_thread(agent_checkpointer.init_checkpointer, settings.REDIS_URL)
    # 启动项目开启异步的扫描任务
    task = asyncio.create_task(reservation_service.run_expire_scan())
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.to_thread(agent_checkpointer.close_checkpointer)


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api)

app.add_exception_handler(BusinessException, business_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/")
def root():
    """健康探活根路径"""
    return {"message": "Hello FastAPI"}
