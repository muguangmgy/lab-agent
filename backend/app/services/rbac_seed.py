"""RBAC 幂等种子数据（角色 / 菜单 / 绑定）。不含旧 users.role 列迁移。"""

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.menu import Menu
from app.models.role import Role
from app.models.user import User

# 种子菜单：path 必须与前端路由一致（/manager/...）
SEED_MENUS = [
    {
        "name": "系统首页",
        "type": "menu",
        "path": "/manager/home",
        "icon": "Menu",
        "sort": 10,
        "roles": ["admin", "student"],
    },
    {
        "name": "AI智能助手",
        "type": "menu",
        "path": "/manager/ai-chat",
        "icon": "ChatDotRound",
        "sort": 20,
        "roles": ["admin", "student"],
    },
    {
        "name": "实验室列表",
        "type": "menu",
        "path": "/manager/lablist",
        "icon": "OfficeBuilding",
        "sort": 30,
        "roles": ["student"],
    },
    {
        "name": "实验室管理",
        "type": "menu",
        "path": "/manager/lab",
        "icon": "House",
        "sort": 40,
        "roles": ["admin"],
    },
    {
        "name": "设备列表管理",
        "type": "menu",
        "path": "/manager/equipment",
        "icon": "Setting",
        "sort": 50,
        "roles": ["admin"],
    },
    {
        "name": "用户管理",
        "type": "menu",
        "path": "/manager/user",
        "icon": "User",
        "sort": 60,
        "roles": ["admin"],
    },
    {
        "name": "我的预约",
        "type": "menu",
        "path": "/manager/my-reservation",
        "icon": "Tickets",
        "sort": 70,
        "roles": ["student"],
    },
    {
        "name": "预约审核",
        "type": "menu",
        "path": "/manager/audit-reservation",
        "icon": "DocumentChecked",
        "sort": 80,
        "roles": ["admin"],
    },
    {
        "name": "实验室设备",
        "type": "menu",
        "path": "/manager/lab-equipment",
        "icon": "Cpu",
        "sort": 90,
        "visible": 0,
        "roles": ["admin", "student"],
    },
    {
        "name": "角色管理",
        "type": "menu",
        "path": "/manager/role",
        "icon": "Avatar",
        "sort": 100,
        "roles": ["admin"],
    },
    {
        "name": "菜单管理",
        "type": "menu",
        "path": "/manager/menu",
        "icon": "Grid",
        "sort": 110,
        "roles": ["admin"],
    },
]


def seed_rbac() -> None:
    """幂等写入角色、菜单、role_menus；无角色的用户兜底绑定 student。"""
    db = SessionLocal()
    try:
        role_defs = [
            ("admin", "管理员"),
            ("student", "学生"),
        ]
        role_map: dict[str, Role] = {}
        for code, name in role_defs:
            role = db.query(Role).filter(Role.code == code).first()
            if not role:
                role = Role(code=code, name=name, status=1)
                db.add(role)
                db.flush()
            role_map[code] = role
        db.commit()

        for code in list(role_map.keys()):
            role_map[code] = db.query(Role).filter(Role.code == code).first()

        for item in SEED_MENUS:
            path = item["path"]
            menu = db.query(Menu).filter(Menu.path == path).first()
            if not menu:
                menu = Menu(
                    name=item["name"],
                    type=item.get("type", "menu"),
                    path=path,
                    icon=item.get("icon"),
                    sort=item.get("sort", 0),
                    visible=item.get("visible", 1),
                    status=1,
                    permission=None,
                )
                db.add(menu)
                db.flush()
            else:
                menu.name = item["name"]
                menu.icon = item.get("icon") or menu.icon
                menu.sort = item.get("sort", menu.sort)
                if "visible" in item:
                    menu.visible = item["visible"]

            for role_code in item.get("roles", []):
                role = role_map.get(role_code)
                if not role:
                    continue
                if menu not in role.menus:
                    role.menus.append(menu)
        db.commit()

        student = role_map.get("student")
        if student:
            users = db.query(User).all()
            for user in users:
                if not user.roles:
                    user.roles.append(student)
            db.commit()
    finally:
        db.close()
