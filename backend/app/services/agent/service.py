from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessage,
    AIMessageChunk,
    BaseMessage,
)
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
        """Agent 节点：用 llm.stream 聚合，既出 token 又得到带 tool_calls 的完整消息。

        stream_mode=messages 依赖可流式的模型调用；最后仍返回一条消息给 tools_condition。
        """
        merged = None
        for chunk in llm.stream(state["messages"]):
            merged = chunk if merged is None else merged + chunk
        if merged is None:
            raise BusinessException(message="大模型没有任何返回内容")
        return {"messages": [merged]}

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


def _content_to_text(content) -> str:
    """把 AI content（str 或多模态 list）收成可见纯文本。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
            else:
                text = getattr(part, "text", None)
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return str(content)


def _extract_assistant_text(messages: list) -> str:
    """从图执行结果中取最后一条非空 AI 文本回复。"""
    if not messages:
        raise BusinessException(message="大模型没有任何返回内容")
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content:
            content = _content_to_text(message.content).strip()
            if content:
                return content
    raise BusinessException(message="大模型没有任何返回内容")


def visible_assistant_delta(chunk) -> str:
    """SSE 只推用户可见 assistant 文本增量。

    过滤 ToolMessage、完整 AIMessage、以及只有 tool_calls 没有正文的块（工具回合不上屏）。
    """
    if not isinstance(chunk, AIMessageChunk):
        return ""
    text = _content_to_text(chunk.content)
    tool_calls = getattr(chunk, "tool_calls", None) or []
    tool_call_chunks = getattr(chunk, "tool_call_chunks", None) or []
    extra = getattr(chunk, "additional_kwargs", None) or {}
    has_tools = bool(tool_calls or tool_call_chunks or extra.get("tool_calls"))
    if has_tools and not text.strip():
        return ""
    return text


def build_input_messages(
    *,
    has_checkpoint: bool,
    last_user_text: str,
    prior_messages: list | None,
) -> list[BaseMessage]:
    """stream_agent / run_agent 共用输入：有 Redis 则暖启动只追加 Human，否则冷启动带 System+prior。"""
    text = (last_user_text or "").strip()
    if has_checkpoint:
        return [HumanMessage(content=text)]
    prior = _prior_to_langchain(prior_messages or [])
    return [
        SystemMessage(content=SYSTEM_PROMPT),
        *prior,
        HumanMessage(content=text),
    ]


def human_already_in_checkpoint(messages: list, last_user_text: str) -> bool:
    """SSE 降级用：stream 可能已把本轮 Human 写入 Redis，invoke 时不能再追加同一句。"""
    text = (last_user_text or "").strip()
    for message in reversed(messages or []):
        if isinstance(message, HumanMessage):
            return (message.content or "").strip() == text
    return False


def final_assistant_from_state(messages: list) -> str | None:
    """若图已停在无 tool_calls 的最终 AI，直接抽出全文。"""
    if not messages:
        return None
    last = messages[-1]
    if isinstance(last, AIMessageChunk) or not isinstance(last, AIMessage):
        return None
    if getattr(last, "tool_calls", None):
        return None
    try:
        return _extract_assistant_text([last])
    except BusinessException:
        return None


def map_agent_exception(exc: Exception) -> BusinessException:
    """run_agent 与 SSE error 共用：Redis 不可用 / 模型失败转成固定中文文案。"""
    if isinstance(exc, BusinessException):
        return exc
    name = type(exc).__module__ + "." + type(exc).__name__
    if "redis" in name.lower() or "Redis" in type(exc).__name__:
        return BusinessException(message=_REDIS_UNAVAILABLE)
    return BusinessException(message="大模型调用失败，请稍后重试")


def _graph_config(thread_id: str) -> dict:
    return {
        "configurable": {"thread_id": str(thread_id).strip()},
        "recursion_limit": 10,
    }


def _validate_run_args(thread_id: str, last_user_text: str) -> str:
    text = (last_user_text or "").strip()
    if not text:
        raise BusinessException(message="请输入您要对话的内容")
    if not thread_id or not str(thread_id).strip():
        raise BusinessException(message="会话无效")
    return text


def _load_checkpoint_messages(agent, config) -> list:
    try:
        state = agent.get_state(config)
        return list((state.values or {}).get("messages") or [])
    except BusinessException:
        raise
    except Exception:
        raise BusinessException(message=_REDIS_UNAVAILABLE)


def _invoke_graph(agent, payload, config):
    try:
        return agent.invoke(payload, config=config)
    except BusinessException:
        raise
    except Exception as exc:
        raise map_agent_exception(exc)


def _resume_without_new_human(agent, config, existing: list) -> str:
    """SSE 未吐字降级：checkpoint 已有本轮 Human 时，抽最终 AI 或空 messages 续跑。"""
    done = final_assistant_from_state(existing)
    if done:
        return done
    result = _invoke_graph(agent, {"messages": []}, config)
    return _extract_assistant_text((result or {}).get("messages") or [])


def run_agent(
    db: Session,
    current_user: User,
    *,
    thread_id: str,
    last_user_text: str,
    prior_messages: list | None = None,
    resume_without_duplicate_human: bool = False,
) -> str:
    """非流式 /chat 以及 SSE 同连接降级：invoke 整图，返回最终可见 assistant 全文。

    resume_without_duplicate_human=True 仅给 stream 失败后的降级：避免 Redis 已有 Human 再写一遍。
    """
    text = _validate_run_args(thread_id, last_user_text)

    agent = build_agent(db, current_user, last_user_text=text)
    config = _graph_config(thread_id)
    existing = _load_checkpoint_messages(agent, config)
    has_checkpoint = bool(existing)

    if (
        resume_without_duplicate_human
        and has_checkpoint
        and human_already_in_checkpoint(existing, text)
    ):
        return _resume_without_new_human(agent, config, existing)

    input_messages = build_input_messages(
        has_checkpoint=has_checkpoint,
        last_user_text=text,
        prior_messages=prior_messages,
    )
    result = _invoke_graph(agent, {"messages": input_messages}, config)
    return _extract_assistant_text((result or {}).get("messages") or [])


def stream_agent(
    db: Session,
    current_user: User,
    *,
    thread_id: str,
    last_user_text: str,
    prior_messages: list | None = None,
):
    """SSE 用：按 token yield 可见文本；冷暖启动与 run_agent 相同（checkpoint / MySQL prior）。

    stream_mode=messages 产出 (chunk, metadata)；只把 visible_assistant_delta 非空的片段交给生成器打 delta。
    """
    text = _validate_run_args(thread_id, last_user_text)

    agent = build_agent(db, current_user, last_user_text=text)
    config = _graph_config(thread_id)
    existing = _load_checkpoint_messages(agent, config)
    has_checkpoint = bool(existing)
    input_messages = build_input_messages(
        has_checkpoint=has_checkpoint,
        last_user_text=text,
        prior_messages=prior_messages,
    )

    try:
        stream = agent.stream(
            {"messages": input_messages},
            config=config,
            stream_mode="messages",
        )
        for item in stream:
            # LangGraph messages 模式多为 (AIMessageChunk, metadata)
            if isinstance(item, tuple) and len(item) >= 1:
                chunk = item[0]
            else:
                chunk = item
            piece = visible_assistant_delta(chunk)
            if piece:
                yield piece
    except BusinessException:
        raise
    except Exception as exc:
        raise map_agent_exception(exc)
