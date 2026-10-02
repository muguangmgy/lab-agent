from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.response import Response
from app.database import get_db
from app.dependencies.auth import require_roles
from app.models.user import User
from app.schemas.role import (
    RoleCreateRequest,
    RoleMenusUpdateRequest,
    RoleUpdateRequest,
)
from app.services import role_service

router = APIRouter(prefix="/role", tags=["角色管理"])


@router.get("/list")
def get_role_list(
    keywords: str | None = None,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """查询角色全量列表（需 admin；可按编码/名称筛选）"""
    res = role_service.get_role_list(db, keywords)
    return Response.success(data=res)


@router.get("/page")
def get_role_page(
    page: int = 1,
    page_size: int = 10,
    keywords: str | None = None,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """分页查询角色列表（需 admin）"""
    res = role_service.get_role_page_list(db, page, page_size, keywords)
    return Response.success(data=res)


@router.post("")
def create_role(
    data: RoleCreateRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """新增角色（需 admin）"""
    res = role_service.create_role(db, data)
    return Response.success(data=res)


@router.put("/{role_id}")
def update_role(
    role_id: int,
    data: RoleUpdateRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """更新角色（需 admin）"""
    res = role_service.update_role(db, role_id, data)
    return Response.success(data=res)


@router.delete("/{role_id}")
def delete_role(
    role_id: int,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """删除角色（需 admin；内置角色不可删）"""
    role_service.delete_role(db, role_id)
    return Response.success(message="删除成功")


@router.put("/{role_id}/menus")
def update_role_menus(
    role_id: int,
    data: RoleMenusUpdateRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """覆盖绑定角色菜单（需 admin）"""
    res = role_service.update_role_menus(db, role_id, data)
    return Response.success(data=res)
