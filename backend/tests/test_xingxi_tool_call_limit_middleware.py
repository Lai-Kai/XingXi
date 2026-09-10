from unittest.mock import MagicMock

from _agent_e2e_helpers import FakeToolCallingModel
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from deerflow.agents.middlewares.xingxi_tool_call_limit_middleware import (
    XingxiToolCallLimitMiddleware,
)


def _runtime(run_id: str = "run-1"):
    runtime = MagicMock()
    runtime.context = {"thread_id": "thread-1", "run_id": run_id}
    return runtime


def _call(call_id: str, name: str = "search_sources") -> dict:
    return {"name": name, "id": call_id, "args": {"query": "吴江沿革"}}


def test_allows_calls_until_mode_budget_then_forces_terminal_response() -> None:
    middleware = XingxiToolCallLimitMiddleware(max_tool_calls=3)
    runtime = _runtime()
    state = {
        "messages": [
            HumanMessage(content="研究吴江县历史沿革"),
            AIMessage(content="", tool_calls=[_call("call-1")]),
            AIMessage(content="", tool_calls=[_call("call-2")]),
            AIMessage(content="", tool_calls=[_call("call-3")]),
            AIMessage(
                content="",
                tool_calls=[_call("call-4")],
                response_metadata={"finish_reason": "tool_calls"},
            ),
        ]
    }

    result = middleware.after_model(state, runtime)

    assert result is not None
    stopped = result["messages"][0]
    assert stopped.tool_calls == []
    assert "工具调用预算已用完" in stopped.content
    assert stopped.response_metadata["finish_reason"] == "stop"
    assert runtime.context["stop_reason"] == "tool_call_limit_capped"


def test_keeps_only_remaining_calls_from_a_parallel_model_response() -> None:
    middleware = XingxiToolCallLimitMiddleware(max_tool_calls=3)
    state = {
        "messages": [
            HumanMessage(content="研究吴江县历史沿革"),
            AIMessage(content="", tool_calls=[_call("call-1"), _call("call-2")]),
            AIMessage(
                content="",
                tool_calls=[_call("call-3"), _call("call-4")],
            ),
        ]
    }

    result = middleware.after_model(state, _runtime())

    assert result is not None
    assert [call["id"] for call in result["messages"][0].tool_calls] == ["call-3"]


def test_does_not_count_tool_calls_from_previous_turn() -> None:
    middleware = XingxiToolCallLimitMiddleware(max_tool_calls=1)
    state = {
        "messages": [
            HumanMessage(content="上一轮"),
            AIMessage(content="", tool_calls=[_call("old-call")]),
            HumanMessage(content="新问题"),
            AIMessage(content="", tool_calls=[_call("new-call")]),
        ]
    }

    assert middleware.after_model(state, _runtime()) is None


def test_capped_parallel_calls_are_not_executed_by_real_agent_graph() -> None:
    executed: list[str] = []

    @tool
    def record(value: str) -> str:
        """Record one value."""
        executed.append(value)
        return f"recorded:{value}"

    model = FakeToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    _call("first", name="record") | {"args": {"value": "one"}},
                    _call("second", name="record") | {"args": {"value": "two"}},
                ],
            ),
            AIMessage(content="finished"),
        ]
    )
    agent = create_agent(
        model=model,
        tools=[record],
        middleware=[XingxiToolCallLimitMiddleware(max_tool_calls=1)],
    )

    result = agent.invoke({"messages": [HumanMessage(content="record both values")]})

    assert executed == ["one"]
    assert [message.tool_call_id for message in result["messages"] if isinstance(message, ToolMessage)] == ["first"]
    assert result["messages"][-1].content == "finished"
