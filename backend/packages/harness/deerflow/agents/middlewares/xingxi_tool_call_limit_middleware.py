"""Bound the number of research-tool calls in one Xingxi turn."""

from __future__ import annotations

from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from deerflow.agents.middlewares.tool_call_metadata import clone_ai_message_with_tool_calls

_TOOL_LIMIT_MESSAGE = (
    "[XINGXI TOOL LIMIT REACHED] 本轮工具调用预算已用完。"
    "请立即使用已经检索到的文献、图谱和时间线结果整理结论；"
    "不要再发起新的工具调用，并明确说明证据范围与不足。"
)


def _append_text(content: Any, text: str) -> Any:
    if content is None:
        return text
    if isinstance(content, str):
        return f"{content}\n\n{text}" if content else text
    if isinstance(content, list):
        return [*content, {"type": "text", "text": f"\n\n{text}"}]
    return f"{content}\n\n{text}"


def _tool_call_key(tool_call: Any, message_index: int, call_index: int) -> str:
    if isinstance(tool_call, dict):
        call_id = tool_call.get("id")
        if isinstance(call_id, str) and call_id:
            return call_id
    return f"message-{message_index}-tool-{call_index}"


class XingxiToolCallLimitMiddleware(AgentMiddleware[AgentState]):
    """Stop a Xingxi turn after its mode-specific research-tool budget.

    The count is derived from the current state rather than mutable middleware
    state, so concurrent runs cannot consume one another's budget. Calls from
    previous user turns are ignored, while calls already present in the current
    turn are counted even when the model emitted them in parallel.
    """

    def __init__(self, max_tool_calls: int) -> None:
        super().__init__()
        if isinstance(max_tool_calls, bool) or not isinstance(max_tool_calls, int):
            raise ValueError("max_tool_calls must be a non-negative integer")
        self.max_tool_calls = max(0, max_tool_calls)

    @staticmethod
    def _current_turn_start(messages: list[Any]) -> int:
        last_user_index = -1
        for index, message in enumerate(messages):
            if not isinstance(message, HumanMessage):
                continue
            if (message.additional_kwargs or {}).get("hide_from_ui") is True:
                continue
            last_user_index = index
        return last_user_index + 1

    @classmethod
    def _count_tool_calls(cls, messages: list[Any], *, end: int | None = None) -> int:
        start = cls._current_turn_start(messages)
        seen: set[str] = set()
        selected = messages[start:] if end is None else messages[start:end]
        for offset, message in enumerate(selected, start=start):
            if not isinstance(message, AIMessage):
                continue
            for call_index, tool_call in enumerate(message.tool_calls or ()):
                seen.add(_tool_call_key(tool_call, offset, call_index))
        return len(seen)

    def _apply(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        messages = list(state.get("messages") or [])
        if not messages or not isinstance(messages[-1], AIMessage):
            return None

        last_message = messages[-1]
        tool_calls = list(last_message.tool_calls or ())
        if not tool_calls:
            return None

        prior_count = self._count_tool_calls(messages, end=len(messages) - 1)
        remaining = max(0, self.max_tool_calls - prior_count)
        if len(tool_calls) <= remaining:
            return None

        kept_tool_calls = tool_calls[:remaining]
        if remaining == 0:
            context = getattr(runtime, "context", None)
            if isinstance(context, dict):
                context["stop_reason"] = "tool_call_limit_capped"
            updated = clone_ai_message_with_tool_calls(
                last_message,
                [],
                content=_append_text(last_message.content, _TOOL_LIMIT_MESSAGE),
            )
        else:
            updated = clone_ai_message_with_tool_calls(
                last_message,
                kept_tool_calls,
            )
        return {"messages": [updated]}

    @override
    def after_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        return self._apply(state, runtime)

    @override
    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        return self._apply(state, runtime)
