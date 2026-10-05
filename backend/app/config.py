from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # 后端项目的根路径


class Settings(BaseSettings):
    JWT_SECRET_KEY: str
    DATABASE_URL: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24
    # LLM
    LLM_API_KEY: str
    LLM_BASE_URL: str
    LLM_MODEL: str
    # Embedding（硅基流动等 OpenAI 兼容接口）
    EMBEDDING_API_KEY: str
    EMBEDDING_BASE_URL: str
    EMBEDDING_MODEL: str
    # Redis（LangGraph Checkpointer）
    REDIS_URL: str = "redis://127.0.0.1:6379"
    # 知识库 md 与 Chroma 持久化目录（相对路径相对 backend 根目录）
    KB_DIR: str = "data/kb"
    CHROMA_DIR: str = "data/chroma"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8"
    )


settings = Settings()


def resolve_data_path(value: str) -> Path:
    """环境变量里的目录：绝对路径原样用，相对路径接到 backend 根目录。"""
    path = Path(value)
    if path.is_absolute():
        return path
    return (BASE_DIR / path).resolve()

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".zip",
}
