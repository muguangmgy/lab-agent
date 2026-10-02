from sqlalchemy.orm import Session, joinedload

from app.common.exceptions import BusinessException
from app.models.menu import Menu
from app.models.role import Role
from app.models.user import User
from app.schemas.menu import MenuCreateRequest, MenuResponse, MenuUpdateRequest


def _to_node(menu: Menu, include_children: bool = True) -> MenuResponse:
    """把菜单 ORM 递归转为树节点（CRUD 单条返回时可不带子树）。"""
    children: list[MenuResponse] = []
    if include_children and menu.children:
        sorted_children = sorted(menu.children, key=lambda m: (m.sort, m.id))
        children = [_to_node(c) for c in sorted_children]
    return MenuResponse(
        id=menu.id,
        parent_id=menu.parent_id,
        name=menu.name,
        type=menu.type,
        path=menu.path,
        component=menu.component,
        icon=menu.icon,
        permission=menu.permission,
        sort=menu.sort,
        visible=menu.visible,
        status=menu.status,
        children=children,
    )


def build_menu_tree(menus: list[Menu]) -> list[MenuResponse]:
    """将扁平菜单列表组装为树。"""
    by_id = {m.id: m for m in menus}
    # 仅用传入集合内的父子关系
    roots: list[Menu] = []
    children_map: dict[int | None, list[Menu]] = {}
    for m in menus:
        parent_id = m.parent_id if m.parent_id in by_id else None
        children_map.setdefault(parent_id, []).append(m)
    for pid in children_map:
        children_map[pid].sort(key=lambda x: (x.sort, x.id))

    def build(nodes: list[Menu]) -> list[MenuResponse]:
        """递归组装子树，仅存在于闭包内供 build_menu_tree 调用。"""
        result = []
        for node in nodes:
            kids = children_map.get(node.id, [])
            item = MenuResponse(
                id=node.id,
                parent_id=node.parent_id,
                name=node.name,
                type=node.type,
                path=node.path,
                component=node.component,
                icon=node.icon,
                permission=node.permission,
                sort=node.sort,
                visible=node.visible,
                status=node.status,
                children=build(kids),
            )
            result.append(item)
        return result

    roots = children_map.get(None, [])
    return build(roots)


def get_menu_tree(db: Session) -> list[MenuResponse]:
    """查询全量菜单并组装为树"""
    menus = db.query(Menu).order_by(Menu.sort.asc(), Menu.id.asc()).all()
    return build_menu_tree(menus)


def get_my_menus(db: Session, user: User) -> list[MenuResponse]:
    """当前用户多角色菜单并集（启用）；侧栏再按 visible 过滤。"""
    user = (
        db.query(User)
        .options(joinedload(User.roles).joinedload(Role.menus))
        .filter(User.id == user.id)
        .first()
    )
    if not user:
        return []
    menu_map: dict[int, Menu] = {}
    for role in user.roles or []:
        if role.status != 1:
            continue
        for menu in role.menus or []:
            if menu.status == 1:
                menu_map[menu.id] = menu
    return build_menu_tree(list(menu_map.values()))


def create_menu(db: Session, data: MenuCreateRequest) -> MenuResponse:
    """新增菜单（父节点须存在）"""
    if data.parent_id is not None:
        parent = db.query(Menu).filter(Menu.id == data.parent_id).first()
        if not parent:
            raise BusinessException(message="父菜单不存在")
    menu = Menu(**data.model_dump())
    db.add(menu)
    db.commit()
    db.refresh(menu)
    return _to_node(menu, include_children=False)


def update_menu(db: Session, menu_id: int, data: MenuUpdateRequest) -> MenuResponse:
    """更新菜单（禁止自引用父节点）"""
    menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not menu:
        raise BusinessException(message="菜单不存在")
    payload = data.model_dump(exclude_none=True)
    if "parent_id" in payload:
        parent_id = payload["parent_id"]
        if parent_id == menu_id:
            raise BusinessException(message="不能将自己设为父菜单")
        if parent_id is not None:
            parent = db.query(Menu).filter(Menu.id == parent_id).first()
            if not parent:
                raise BusinessException(message="父菜单不存在")
    for field, value in payload.items():
        setattr(menu, field, value)
    db.commit()
    db.refresh(menu)
    return _to_node(menu, include_children=False)


def delete_menu(db: Session, menu_id: int) -> None:
    """删除菜单（有子菜单或角色绑定时拒绝）"""
    menu = (
        db.query(Menu)
        .options(joinedload(Menu.children), joinedload(Menu.roles))
        .filter(Menu.id == menu_id)
        .first()
    )
    if not menu:
        raise BusinessException(message="菜单不存在")
    if menu.children:
        raise BusinessException(message="存在子菜单，无法删除")
    if menu.roles:
        raise BusinessException(message="该菜单仍有角色绑定，无法删除")
    db.delete(menu)
    db.commit()
