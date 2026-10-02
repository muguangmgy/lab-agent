from sqlalchemy.orm import Session, joinedload

from app.common.exceptions import BusinessException
from app.common.response import PageResponse
from app.models.menu import Menu
from app.models.role import Role
from app.schemas.role import (
    RoleCreateRequest,
    RoleMenusUpdateRequest,
    RoleResponse,
    RoleUpdateRequest,
)


def _to_response(role: Role) -> RoleResponse:
    """将 Role ORM 转为含 menu_ids 的响应。"""
    return RoleResponse(
        id=role.id,
        code=role.code,
        name=role.name,
        status=role.status,
        remark=role.remark,
        menu_ids=[m.id for m in (role.menus or [])],
    )


def get_role_list(db: Session, keywords: str | None = None) -> list[RoleResponse]:
    """按关键词筛选角色全量列表"""
    query = db.query(Role).options(joinedload(Role.menus))
    if keywords:
        like = f"%{keywords}%"
        query = query.filter((Role.code.ilike(like)) | (Role.name.ilike(like)))
    roles = query.order_by(Role.id.asc()).all()
    return [_to_response(r) for r in roles]


def get_role_page_list(
    db: Session, page: int, page_size: int, keywords: str | None = None
) -> PageResponse:
    """分页查询角色列表"""
    query = db.query(Role)
    if keywords:
        like = f"%{keywords}%"
        query = query.filter((Role.code.ilike(like)) | (Role.name.ilike(like)))
    total = query.count()
    items = (
        query.options(joinedload(Role.menus))
        .order_by(Role.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PageResponse(list=[_to_response(r) for r in items], total=total)


def create_role(db: Session, data: RoleCreateRequest) -> RoleResponse:
    """新增角色（编码唯一）"""
    exists = db.query(Role).filter(Role.code == data.code).first()
    if exists:
        raise BusinessException(message="角色编码已存在")
    role = Role(
        code=data.code,
        name=data.name,
        status=data.status,
        remark=data.remark,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return _to_response(role)


def update_role(db: Session, role_id: int, data: RoleUpdateRequest) -> RoleResponse:
    """更新角色基本信息（改编码时校验唯一）"""
    role = (
        db.query(Role)
        .options(joinedload(Role.menus))
        .filter(Role.id == role_id)
        .first()
    )
    if not role:
        raise BusinessException(message="角色不存在")
    payload = data.model_dump(exclude_none=True)
    if "code" in payload and payload["code"] != role.code:
        exists = db.query(Role).filter(Role.code == payload["code"]).first()
        if exists:
            raise BusinessException(message="角色编码已存在")
    for field, value in payload.items():
        setattr(role, field, value)
    db.commit()
    db.refresh(role)
    return _to_response(role)


def delete_role(db: Session, role_id: int) -> None:
    """删除角色（有用户绑定或内置角色时拒绝）"""
    role = (
        db.query(Role)
        .options(joinedload(Role.users), joinedload(Role.menus))
        .filter(Role.id == role_id)
        .first()
    )
    if not role:
        raise BusinessException(message="角色不存在")
    if role.users:
        raise BusinessException(message="该角色仍有用户绑定，无法删除")
    if role.code in ("admin", "student"):
        raise BusinessException(message="系统内置角色不可删除")
    role.menus.clear()
    db.delete(role)
    db.commit()


def update_role_menus(
    db: Session, role_id: int, data: RoleMenusUpdateRequest
) -> RoleResponse:
    """覆盖写入角色与菜单的绑定关系"""
    role = (
        db.query(Role)
        .options(joinedload(Role.menus))
        .filter(Role.id == role_id)
        .first()
    )
    if not role:
        raise BusinessException(message="角色不存在")
    menus = []
    if data.menu_ids:
        menus = db.query(Menu).filter(Menu.id.in_(data.menu_ids)).all()
        if len(menus) != len(set(data.menu_ids)):
            raise BusinessException(message="存在无效的菜单ID")
    role.menus = menus
    db.commit()
    role = (
        db.query(Role)
        .options(joinedload(Role.menus))
        .filter(Role.id == role_id)
        .first()
    )
    return _to_response(role)
