from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.common.exceptions import BusinessException
from app.models.user import User
from app.services.agent.tools import build_tools
from app.services.agent.checkpointer import get_checkpointer
from app.config import settings

SYSTEM_PROMPT = """你是智能实验室预约系统的 Agent，回答要简洁。
你可以：
1. 使用 search_lab_docs 查询实验室的规则、安全、开放时间等问题
2. 使用 list_open_labs / list_lab_equipments  查询真实的实验室和设备
3. 在用户进行了预约确认后，使用 create_lab_reservation 来进行真实的预约落库
4. 使用 get_today 来进行日期的换算

## 必须遵守
当用户提到了 今天、明天、后天 等日期相关的问题，请先调用 get_today 来获取日期，**不要直接返回 我需要确定明天的具体日期**。

在提交预约之前必须向用户复述：实验室ID与名称（或设备ID和名称）、日期、开始时间、结束时间。并得到用户确认再进行实际操作。
用户没说【确认】【确认预约】【就这样预约】等确定性回复之前，不要调用 create_lab_reservation。
工作流的确认环节里如果缺少了 lab_id，请先 list_open_labs 查到了 lab_id 再创建，不要瞎写。
工作流的确认环节里如果缺少了 equipment_id，请先 list_lab_equipments 查到了 equipment_id 再创建，不要瞎写。

预约成功后状态是待审核，必须管理员确认后实验室（或设备）才能使用。
不要瞎编数据库里没有的实验室或者设备信息。
如果是问开放时间或者实验室规则，优先调用 search_lab_docs，不要凭空回复。
"""

_REDIS_UNAVAILABLE = "对话服务暂不可用，请稍后重试"


def build_agent(db: Session, current_user: User, last_user_text: str = ""):
    """组装带 tools 与 Redis checkpointer 的 LangGraph Agent。"""
    tools = build_tools(db, current_user, last_user_text=last_user_text)
    llm = ChatOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        temperature=0,
    ).bind_tools(tools)

    def agent_node(state: MessagesState):
        """langGraph 执行的工作流 的节点"""
        response = llm.invoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)  # 调用大模型的节点
    graph.add_node("tools", ToolNode(tools))  # tool call的节点
    graph.add_edge(START, "agent")  # 流程的起点，call LLM
    graph.add_conditional_edges(
        "agent", tools_condition
    )  # 看有无 tool_call  有就继续call  没有就END 输出
    graph.add_edge("tools", "agent")  # 让agent看tool调用的结果
    return graph.compile(checkpointer=get_checkpointer())


def _prior_to_langchain(prior_messages: list) -> list[BaseMessage]:
    """MySQL 历史 → Human/AI（无 ToolMessage），用于 Redis 无 checkpoint 时冷启动。"""
    history: list[BaseMessage] = []
    for message in prior_messages or []:
        role = getattr(message, "role", None)
        content = (getattr(message, "content", None) or "").strip()
        if not content:
            continue
        if role == "user":
            history.append(HumanMessage(content=content))
        elif role == "assistant":
            history.append(AIMessage(content=content))
    return history


def _extract_assistant_text(messages: list) -> str:
    """从图执行结果中取最后一条非空 AI 文本回复。"""
    if not messages:
        raise BusinessException(message="大模型没有任何返回内容")
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content:
            content = message.content
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            content = str(content).strip()
            if content:
                return content
    raise BusinessException(message="大模型没有任何返回内容")


def run_agent(
    db: Session,
    current_user: User,
    *,
    thread_id: str,
    last_user_text: str,
    prior_messages: list | None = None,
) -> str:
    """多轮对话：有 Redis checkpoint 只追加本轮 Human；否则 MySQL 冷启动。"""
    text = (last_user_text or "").strip()
    if not text:
        raise BusinessException(message="请输入您要对话的内容")
    if not thread_id or not str(thread_id).strip():
        raise BusinessException(message="会话无效")

    agent = build_agent(db, current_user, last_user_text=text)
    config = {
        "configurable": {"thread_id": thread_id.strip()},
        "recursion_limit": 10,
    }

    try:
        state = agent.get_state(config)
        has_checkpoint = bool((state.values or {}).get("messages"))
    except BusinessException:
        raise
    except Exception:
        raise BusinessException(message=_REDIS_UNAVAILABLE)

    if has_checkpoint:
        input_messages: list[BaseMessage] = [HumanMessage(content=text)]
    else:
        prior = _prior_to_langchain(prior_messages or [])
        input_messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            *prior,
            HumanMessage(content=text),
        ]

    try:
        result = agent.invoke({"messages": input_messages}, config=config)
    except BusinessException:
        raise
    except Exception as exc:
        # Redis / 网络类优先友好提示
        name = type(exc).__module__ + "." + type(exc).__name__
        if "redis" in name.lower() or "Redis" in type(exc).__name__:
            raise BusinessException(message=_REDIS_UNAVAILABLE)
        raise BusinessException(message="大模型调用失败，请稍后重试")

    return _extract_assistant_text(result.get("messages") or [])
