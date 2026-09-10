"""Product-level behavior for the Xingxi runtime."""

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace


def test_gateway_defaults_every_new_run_to_xingxi():
    from app.gateway import services

    assert services._DEFAULT_ASSISTANT_ID == "xingxi"


def test_gateway_resolves_the_xingxi_product_factory():
    from app.gateway.services import resolve_agent_factory

    factory = resolve_agent_factory("xingxi")

    assert factory.__name__ == "make_xingxi_agent"
    assert factory.__module__ == "deerflow.agents.xingxi.agent"


def test_xingxi_factory_injects_product_evidence_tools(monkeypatch):
    import deerflow.config as deerflow_config
    from deerflow.agents.lead_agent import agent as lead_agent_module
    from deerflow.agents.middlewares.xingxi_tool_call_limit_middleware import (
        XingxiToolCallLimitMiddleware,
    )
    from deerflow.agents.xingxi.agent import make_xingxi_agent

    captured = {}

    def fake_make_lead_agent(config, **kwargs):
        captured.update(kwargs)
        return "xingxi-graph"

    monkeypatch.setattr(lead_agent_module, "_make_lead_agent", fake_make_lead_agent)
    monkeypatch.setattr(deerflow_config, "get_app_config", lambda: object())

    assert make_xingxi_agent({"configurable": {}}) == "xingxi-graph"
    assert [tool.name for tool in captured["additional_tools"]] == [
        "search_sources",
        "query_knowledge_graph",
        "query_timeline",
        "query_map_features",
        "gloss_ancient_text",
        "resolve_name_variants",
    ]
    assert captured["include_default_tools"] is False
    assert captured["include_skill_tools"] is False
    assert captured["system_prompt_override"]
    assert "system_prompt_extension" not in captured
    limit_middlewares = [
        item
        for item in captured["custom_middlewares"]
        if isinstance(item, XingxiToolCallLimitMiddleware)
    ]
    assert len(limit_middlewares) == 1
    assert limit_middlewares[0].max_tool_calls == 3
    captured.clear()
    assert make_xingxi_agent({"configurable": {"mode": "pro"}}) == "xingxi-graph"
    assert [tool.name for tool in captured["additional_tools"]] == [
        "search_sources",
        "query_knowledge_graph",
        "query_timeline",
        "query_map_features",
        "gloss_ancient_text",
        "resolve_name_variants",
        "compare_sources",
    ]
    limit_middlewares = [
        item
        for item in captured["custom_middlewares"]
        if isinstance(item, XingxiToolCallLimitMiddleware)
    ]
    assert len(limit_middlewares) == 1
    assert limit_middlewares[0].max_tool_calls == 12
    captured.clear()
    assert make_xingxi_agent({"configurable": {"mode": "ultra"}}) == "xingxi-graph"
    assert [tool.name for tool in captured["additional_tools"]] == [
        "search_sources",
        "query_knowledge_graph",
        "query_timeline",
        "query_map_features",
        "gloss_ancient_text",
        "resolve_name_variants",
        "compare_sources",
    ]


def test_xingxi_factory_adds_view_image_for_a_vision_model(monkeypatch):
    import deerflow.config as deerflow_config
    from deerflow.agents.lead_agent import agent as lead_agent_module
    from deerflow.agents.xingxi.agent import make_xingxi_agent

    captured = {}
    vision_model = SimpleNamespace(name="gpt-5.6-luna", supports_vision=True)
    app_config = SimpleNamespace(
        models=[vision_model],
        get_model_config=lambda name: vision_model if name == vision_model.name else None,
    )

    def fake_make_lead_agent(config, **kwargs):
        captured.update(kwargs)
        return "xingxi-graph"

    monkeypatch.setattr(lead_agent_module, "_make_lead_agent", fake_make_lead_agent)
    monkeypatch.setattr(deerflow_config, "get_app_config", lambda: app_config)

    assert make_xingxi_agent({"configurable": {"model_name": "gpt-5.6-luna"}}) == "xingxi-graph"
    assert "view_image" in [tool.name for tool in captured["additional_tools"]]
    assert captured["include_default_tools"] is False


def test_xingxi_prompt_is_project_specific_and_concise():
    from deerflow.agents.xingxi.prompt import XINGXI_SYSTEM_PROMPT

    assert "吴文化" in XINGXI_SYSTEM_PROMPT
    assert "木渎" in XINGXI_SYSTEM_PROMPT
    assert "你能做什么" in XINGXI_SYSTEM_PROMPT
    assert "view_image" in XINGXI_SYSTEM_PROMPT
    for unrelated_capability in ("代码", "README", "PPT", "音频", "视频", "音乐", "DeerFlow"):
        assert unrelated_capability not in XINGXI_SYSTEM_PROMPT


def test_restricted_lead_factory_exposes_only_product_tools(monkeypatch):
    from langchain_core.tools import tool

    from deerflow.agents.lead_agent import agent as lead_agent_module
    from deerflow.config.memory_config import MemoryConfig

    @tool
    def domain_probe() -> str:
        """A product-scoped test tool."""
        return "ok"

    def fail_generic_path(*args, **kwargs):
        raise AssertionError("restricted Xingxi runs must not load generic tools, skills, or prompts")

    monkeypatch.setattr(lead_agent_module, "_resolve_model_name", lambda *args, **kwargs: "model")
    monkeypatch.setattr(lead_agent_module, "create_chat_model", lambda **kwargs: "model")
    monkeypatch.setattr(lead_agent_module, "build_middlewares", lambda *args, **kwargs: [])
    monkeypatch.setattr(lead_agent_module, "create_agent", lambda **kwargs: kwargs)
    monkeypatch.setattr(lead_agent_module, "build_tracing_callbacks", lambda: [])
    monkeypatch.setattr(lead_agent_module, "apply_prompt_template", fail_generic_path)
    monkeypatch.setattr(lead_agent_module, "_load_enabled_available_skills", fail_generic_path)
    monkeypatch.setattr("deerflow.tools.get_available_tools", fail_generic_path)

    app_config = SimpleNamespace(
        get_model_config=lambda name: SimpleNamespace(supports_thinking=True, supports_vision=False),
        memory=MemoryConfig(enabled=True, mode="tool"),
        skills=SimpleNamespace(deferred_discovery=True, container_path="/tmp/skills"),
        tool_search=SimpleNamespace(enabled=False, auto_promote_top_k=0),
    )
    result = lead_agent_module._make_lead_agent(
        {"configurable": {"thinking_enabled": True, "reasoning_effort": "high"}},
        app_config=app_config,
        system_prompt_override="Xingxi only",
        include_default_tools=False,
        include_skill_tools=False,
        additional_tools=[domain_probe],
    )

    assert result["system_prompt"] == "Xingxi only"
    assert [registered.name for registered in result["tools"]] == ["domain_probe"]


def test_xingxi_run_cannot_be_switched_into_a_generic_custom_agent():
    from deerflow.agents.xingxi.agent import prepare_xingxi_config

    source = {
        "configurable": {"agent_name": "another-agent", "is_bootstrap": True, "mode": "flash"},
        "context": {"agent_name": "another-agent", "is_bootstrap": True},
    }

    prepared = prepare_xingxi_config(source)

    assert prepared["configurable"]["mode"] == "flash"
    assert prepared["configurable"]["is_plan_mode"] is False
    assert prepared["configurable"]["subagent_enabled"] is False
    assert prepared["context"] == {}
    assert prepared["metadata"]["product"] == "xingxi"
    assert source["configurable"]["agent_name"] == "another-agent"


def test_xingxi_config_preserves_live_sqlite_connections():
    from deerflow.agents.xingxi.agent import prepare_xingxi_config

    connection = sqlite3.connect(":memory:")
    try:
        prepared = prepare_xingxi_config(
            {
                "configurable": {"thread_id": "thread-1"},
                "runtime": {"connection": connection},
            }
        )

        assert prepared["runtime"]["connection"] is connection
    finally:
        connection.close()


def test_xingxi_is_the_only_registered_langgraph():
    config_path = Path(__file__).resolve().parents[1] / "langgraph.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert config["graphs"] == {"xingxi": "deerflow.agents.xingxi:make_xingxi_agent"}


def test_xingxi_assistant_id_does_not_enable_custom_agent_loading():
    from app.gateway.services import build_run_config

    config = build_run_config("thread-1", None, None, assistant_id="xingxi")

    assert "agent_name" not in config["configurable"]
    assert "agent_name" not in config.get("context", {})


def test_gateway_exposes_xingxi_without_generic_agent_product_routes():
    from app.gateway.app import app
    from app.gateway.routers.assistants_compat import _list_assistants

    paths = {route.path for route in app.routes}
    assistants = _list_assistants()

    assert app.title == "Xingxi API Gateway"
    assert [(item.assistant_id, item.name) for item in assistants] == [("xingxi", "星羲弦沚")]
    assert not any(path == "/api/agents" or path.startswith("/api/agents/") for path in paths)
    assert not any(path == "/api/skills" or path.startswith("/api/skills/") for path in paths)
