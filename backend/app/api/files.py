import os
import time
from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, File, UploadFile

from app.common.exceptions import BusinessException
from app.common.response import Response
from app.config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE, UPLOAD_DIR
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.file import FileResponse

router = APIRouter(prefix="/files", tags=["文件管理"])


@router.post("/upload")
def upload(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """文件上传的接口（需登录）"""
    _ = current_user
    if not file.filename:
        raise BusinessException(message="文件名不能为空")

    original_name = os.path.basename(file.filename)
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise BusinessException(message=f"不支持的文件后缀：{ext}")

    disk_name = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}{ext}"
    save_path = UPLOAD_DIR / disk_name

    written = 0
    chunk_size = 1024 * 1024
    try:
        with open(save_path, "wb") as f:
            while True:
                chunk = file.file.read(chunk_size)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_FILE_SIZE:
                    raise BusinessException(
                        message=f"文件不能超过 {MAX_FILE_SIZE // 1024 // 1024}MB"
                    )
                f.write(chunk)
    except BusinessException:
        if save_path.exists():
            save_path.unlink(missing_ok=True)
        raise
    except Exception:
        if save_path.exists():
            save_path.unlink(missing_ok=True)
        raise BusinessException(message="文件上传失败")

    return Response.success(
        data=FileResponse(
            original_name=original_name,
            disk_name=disk_name,
            size=written,
            url=f"/uploads/{disk_name}",
        )
    )
