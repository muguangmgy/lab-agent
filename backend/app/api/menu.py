from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.response import Response
from app.database import get_db
from app.dependencies.auth import get_current_user, require_roles
from app.models.user import User
from app.schemas.menu import MenuCreateRequest, MenuUpdateRequest
from app.services import menu_service

router = APIRouter(prefix="/menu", tags=["菜单管理"])


@router.get("/my")
def get_my_menus(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当前用户多角色菜单并集"""
    res = menu_service.get_my_menus(db, current_user)
    return Response.success(data=res)


@router.get("/tree")
def get_menu_tree(
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """查询全量菜单树（需 admin）"""
    res = menu_service.get_menu_tree(db)
    return Response.success(data=res)


@router.post("")
def create_menu(
    data: MenuCreateRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """新增菜单（需 admin）"""
    res = menu_service.create_menu(db, data)
    return Response.success(data=res)


@router.put("/{menu_id}")
def update_menu(
    menu_id: int,
    data: MenuUpdateRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """更新菜单（需 admin）"""
    res = menu_service.update_menu(db, menu_id, data)
    return Response.success(data=res)


@router.delete("/{menu_id}")
def delete_menu(
    menu_id: int,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """删除菜单（需 admin；有子菜单或角色绑定时拒绝）"""
    menu_service.delete_menu(db, menu_id)
    return Response.success(message="删除成功")
