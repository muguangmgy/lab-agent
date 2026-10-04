from datetime import datetime
import json
from sqlalchemy.orm import Session
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.common.exceptions import BusinessException
from app.models.user import User
from app.schemas.reservation import ReservationCreateRequest
from app.services import equipment_service, kb_service, lab_service, reservation_service

# 用户明确确认后才允许落库预约（服务端校验，不单靠 Prompt）
_CONFIRM_KEYWORDS = (
    "确认预约",
    "就这样预约",
    "确定预约",
    "确认提交",
    "好的确认",
    "确认",
)


def _user_confirmed(text: str) -> bool:
    """服务端校验用户本轮是否含确认关键词，防止未确认落库。"""
    t = (text or "").strip()
    if not t:
        return False
    return any(k in t for k in _CONFIRM_KEYWORDS)


def _ok(**payload) -> str:
    """统一成功返回：始终含 ok=true。"""
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def _err(error: str) -> str:
    """统一失败返回：始终含 ok=false 与 error。"""
    return json.dumps({"ok": False, "error": error}, ensure_ascii=False)


class SearchLabDocsInput(BaseModel):
    query: str = Field(
        description="检索内容，优先用用户原话或关键词，如预约规则、开放时间、安全规范"
    )


class ListOpenLabsInput(BaseModel):
    keywords: str = Field(
        default="",
        description="可选，按实验室名称/地点模糊搜索；为空则返回开放中的实验室列表",
    )


class ListLabEquipmentsInput(BaseModel):
    lab_id: int = Field(description="实验室 ID，须来自 list_open_labs 的真实结果")
    keywords: str = Field(
        default="",
        description="可选，按设备名称模糊搜索；为空则返回该实验室设备列表",
    )


class CreateLabReservationInput(BaseModel):
    lab_id: int = Field(description="实验室 ID，须来自 list_open_labs，禁止编造")
    date: str = Field(description="预约日期，格式 YYYY-MM-DD")
    start_time: str = Field(description="开始时间，格式 HH:mm，如 14:00")
    end_time: str = Field(description="结束时间，格式 HH:mm，如 16:00")
    equipment_id: int | None = Field(
        default=None,
        description="可选，设备 ID；预约设备时必填，须来自 list_lab_equipments",
    )
    remark: str | None = Field(default=None, description="可选备注")


def build_tools(db: Session, current_user: User, last_user_text: str = ""):
    """闭包注入 db/当前用户/本轮文本，供 Agent 绑定工具。"""

    @tool(args_schema=SearchLabDocsInput)
    def search_lab_docs(query: str) -> str:
        """检索实验室知识库（预约规则、开放时间、安全规范、设备使用说明等）。

        用户询问规则、制度、开放时间、安全要求时优先调用；不要凭空编造。
        """
        try:
            content = kb_service.search(query)
            if not content:
                return _ok(content="", message="没有检索到相关的资料")
            return _ok(content=content)
        except Exception as exc:
            return _err(str(exc))

    @tool(args_schema=ListOpenLabsInput)
    def list_open_labs(keywords: str = "") -> str:
        """查询当前开放中的实验室列表（真实数据库）。

        需要 lab_id、实验室名称、地点或开放时段时调用；预约前若缺少 lab_id 必须先调本工具。
        """
        try:
            keywords = (keywords or "").strip() or None
            page = lab_service.get_lab_page_list(
                db, page=1, page_size=10, keywords=keywords, status=1
            )
            rows = [
                {
                    "id": item.id,
                    "name": item.name,
                    "location": item.location,
                    "capacity": item.capacity,
                    "open_time": item.open_time,
                    "close_time": item.close_time,
                }
                for item in page.list
            ]
            return _ok(total=page.total, labs=rows)
        except Exception as exc:
            return _err(str(exc))

    @tool(args_schema=ListLabEquipmentsInput)
    def list_lab_equipments(lab_id: int, keywords: str = "") -> str:
        """查询某个实验室下的设备列表（真实数据库）。

        用户要预约设备或询问某实验室有哪些设备时调用；缺少 equipment_id 时先调本工具。
        """
        try:
            keywords = (keywords or "").strip() or None
            page = equipment_service.get_equipment_page_list(
                db, page=1, page_size=10, lab_id=int(lab_id), keywords=keywords
            )
            rows = [
                {
                    "id": item.id,
                    "name": item.name,
                    "lab_id": item.lab_id,
                    "lab_name": item.lab_name,
                    "spec": item.spec,
                    "quantity": item.quantity,
                    "status": item.status,
                }
                for item in page.list
            ]
            return _ok(total=page.total, equipments=rows)
        except Exception as exc:
            return _err(str(exc))

    @tool(args_schema=CreateLabReservationInput)
    def create_lab_reservation(
        lab_id: int,
        date: str,
        start_time: str,
        end_time: str,
        equipment_id: int | None = None,
        remark: str | None = None,
    ) -> str:
        """提交真实预约（会落库）。仅当用户本轮已明确确认后才能调用。

        调用前须已向用户复述 lab_id/名称、日期与时段，并得到确认类回复；
        未确认会被服务端拒绝。成功后状态为待审核。
        """
        try:
            if not _user_confirmed(last_user_text):
                return _err(
                    "用户尚未确认预约，请先复述预约信息并等待用户明确回复确认后再提交"
                )
            data = ReservationCreateRequest(
                lab_id=lab_id,
                equipment_id=equipment_id,
                date=date,
                start_time=start_time,
                end_time=end_time,
                remark=remark,
            )
            reservation_service.create_reservation(db, current_user, data)
            return _ok(
                message="预约已提交，请等待管理员审核",
                lab_id=lab_id,
                equipment_id=equipment_id,
                date=date,
                start_time=start_time,
                end_time=end_time,
            )
        except BusinessException as exc:
            return _err(exc.message)
        except Exception as exc:
            return _err(str(exc))

    @tool
    def get_today() -> str:
        """获取服务器今天的日期，格式 YYYY-MM-DD。

        用户提到今天、明天、后天或相对日期时先调用本工具再换算，不要猜测日期。
        """
        return _ok(date=datetime.now().strftime("%Y-%m-%d"))

    return [
        search_lab_docs,
        list_open_labs,
        list_lab_equipments,
        create_lab_reservation,
        get_today,
    ]
