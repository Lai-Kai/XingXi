from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.gateway.services import build_run_config, inject_authenticated_user_context
from deerflow.agents.memory.summarization_hook import memory_flush_hook
from deerflow.agents.memory.tools import get_memory_tools
from deerflow.agents.middlewares.dynamic_context_middleware import DynamicContextMiddleware
from deerflow.agents.middlewares.memory_middleware import MemoryMiddleware
from deerflow.config.memory_config import MemoryConfig, is_memory_enabled_for_identity


def test_excluded_memory_accounts_are_normalized_and_matched_exactly() -> None:
    config = MemoryConfig(excluded_users=[" Test@Example.COM ", "user-123"])

    assert config.excluded_users == frozenset({"test@example.com", "user-123"})
    assert is_memory_enabled_for_identity(config, user_id="user-456", email="test@example.com") is False
    assert is_memory_enabled_for_identity(config, user_id="USER-123") is False
    assert is_memory_enabled_for_identity(config, user_id="user-12") is True


def test_global_memory_disable_still_wins_over_account_policy() -> None:
    config = MemoryConfig(enabled=False, excluded_users=[])

    assert is_memory_enabled_for_identity(config, user_id="ordinary-user") is False


def test_gateway_stamps_server_owned_memory_status_for_excluded_email() -> None:
    config = build_run_config("thread-1", {"context": {"memory_enabled": True}}, None)
    request = SimpleNamespace(
        state=SimpleNamespace(
            user=SimpleNamespace(
                id="test-user-id",
                email="tester@example.com",
                system_role="user",
                oauth_provider=None,
                oauth_id=None,
            ),
            auth_source="session",
        )
    )

    with patch(
        "deerflow.config.memory_config.get_memory_config",
        return_value=MemoryConfig(enabled=True, excluded_users=["tester@example.com"]),
    ):
        inject_authenticated_user_context(config, request)

    assert config["context"]["memory_enabled"] is False


def test_excluded_account_does_not_queue_memory_update() -> None:
    manager = MagicMock()
    middleware = MemoryMiddleware(memory_config=MemoryConfig(enabled=True))
    runtime = SimpleNamespace(
        context={
            "thread_id": "thread-1",
            "user_id": "test-user-id",
            "memory_enabled": False,
        }
    )
    state = {
        "messages": [
            HumanMessage(content="remember this"),
            AIMessage(content="done"),
        ]
    }

    with patch(
        "deerflow.agents.middlewares.memory_middleware.get_memory_manager",
        return_value=manager,
    ):
        middleware.after_agent(state, runtime)

    manager.add.assert_not_called()


def test_excluded_account_does_not_load_memory_context() -> None:
    middleware = DynamicContextMiddleware(memory_enabled=False)
    state = {"messages": [HumanMessage(content="hello", id="message-1")]}

    with patch(
        "deerflow.agents.lead_agent.prompt._get_memory_context",
        side_effect=AssertionError("excluded account must not load memory"),
    ):
        result = middleware.before_agent(state, SimpleNamespace(context={}))

    assert result is not None
    assert len(result["messages"]) == 2
    assert all("<memory>" not in str(message.content) for message in result["messages"])


def test_excluded_account_does_not_flush_memory_before_summarization() -> None:
    manager = MagicMock()
    event = SimpleNamespace(
        thread_id="thread-1",
        runtime=SimpleNamespace(context={"memory_enabled": False}),
        messages_to_summarize=[HumanMessage(content="remember this")],
        agent_name=None,
    )

    with (
        patch("deerflow.agents.memory.summarization_hook.get_memory_config", return_value=MemoryConfig(enabled=True)),
        patch("deerflow.agents.memory.summarization_hook.get_memory_manager", return_value=manager),
    ):
        memory_flush_hook(event)

    manager.add_nowait.assert_not_called()


def test_memory_tools_refuse_excluded_account_without_loading_manager() -> None:
    runtime = SimpleNamespace(context={"memory_enabled": False})

    with patch(
        "deerflow.agents.memory.tools.get_memory_manager",
        side_effect=AssertionError("excluded account must not load the memory manager"),
    ):
        for memory_tool in get_memory_tools():
            kwargs = {"query": "test"} if memory_tool.name == "memory_search" else {}
            if memory_tool.name in {"memory_update", "memory_delete"}:
                kwargs["fact_id"] = "fact-1"
            if memory_tool.name == "memory_add":
                kwargs["content"] = "remember this"
            result = memory_tool.func(runtime, **kwargs)
            assert result == '{"error": "Memory is disabled for this account."}'
