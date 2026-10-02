"""显式导出所有模型，保证 create_all 能建出全部表。"""

from app.models.user import User
from app.models.role import Role, user_roles, role_menus
from app.models.menu import Menu
from app.models.lab import Lab
from app.models.equipment import Equipment
from app.models.reservation import Reservation
from app.models.ai_chat import AiChatSession, AiChatMessage

__all__ = [
    "User",
    "Role",
    "Menu",
    "user_roles",
    "role_menus",
    "Lab",
    "Equipment",
    "Reservation",
    "AiChatSession",
    "AiChatMessage",
]
