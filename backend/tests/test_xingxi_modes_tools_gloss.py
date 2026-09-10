from __future__ import annotations

from wu_culture.gloss import gloss_passage
from wu_culture.modes import XingxiMode, resolve_mode_profile
from wu_culture.tool_registry import list_public_tools


def test_flash_pro_and_ultra_profiles_differ() -> None:
    flash = resolve_mode_profile("flash")
    pro = resolve_mode_profile("pro")
    ultra = resolve_mode_profile("ultra")
    assert flash.mode is XingxiMode.FLASH
    assert pro.mode is XingxiMode.PRO
    assert ultra.mode is XingxiMode.ULTRA
    assert flash.enable_subagents is False
    assert pro.enable_subagents is False
    assert ultra.enable_subagents is False
    assert flash.max_tool_calls < pro.max_tool_calls < ultra.max_tool_calls
    assert flash.max_answer_tokens < pro.max_answer_tokens < ultra.max_answer_tokens
    assert flash.evidence_required and pro.evidence_required and ultra.evidence_required


def test_public_tools_hide_admin_and_respect_mode() -> None:
    flash_tools = {tool.name for tool in list_public_tools("flash")}
    pro_tools = {tool.name for tool in list_public_tools("pro")}
    assert "search_sources" in flash_tools
    assert "query_knowledge_graph" in flash_tools
    assert "query_timeline" in flash_tools
    assert "query_map_features" in flash_tools
    assert "gloss_ancient_text" in flash_tools
    assert "resolve_name_variants" in flash_tools
    assert "publish_release" not in flash_tools
    assert "compare_sources" not in flash_tools
    assert "compare_sources" in pro_tools


def test_gloss_keeps_original_and_marks_uncertainty() -> None:
    passage = "香溪有桥，始建未详。"
    result = gloss_passage(passage)
    assert result.original == passage
    assert result.sentences
    assert any(s.original for s in result.sentences)
    assert any("未详" in s.original or s.uncertain_terms for s in result.sentences)
    assert "权威校注" not in result.sentences[0].modern
    assert "输入篇幅超过上限" in gloss_passage("香溪有桥。", max_chars=2).notes[-1]
    import pytest

    with pytest.raises(ValueError, match="max_chars"):
        gloss_passage("香溪", max_chars=0)


def test_gloss_splits_chinese_sentences_and_explains_terms() -> None:
    result = gloss_passage("缘溪行，忘路之远近。忽逢桃花林，夹岸数百步。")
    assert len(result.sentences) == 2
    assert result.sentences[0].modern.startswith("沿着溪水前行")
    assert {item["term"] for item in result.sentences[1].keywords} == {
        "忽逢",
        "夹岸",
    }


def test_prepare_xingxi_config_maps_mode_flags() -> None:
    from deerflow.agents.xingxi.agent import prepare_xingxi_config

    flash = prepare_xingxi_config({"configurable": {"mode": "flash"}})
    assert flash["configurable"]["is_plan_mode"] is False
    assert flash["configurable"]["subagent_enabled"] is False
    assert flash["configurable"]["thinking_enabled"] is False
    assert flash["configurable"]["reasoning_effort"] == "minimal"
    assert flash["configurable"]["max_tool_calls"] == 3
    assert flash["configurable"]["max_answer_tokens"] == 800
    pro = prepare_xingxi_config({"configurable": {"mode": "pro"}})
    assert pro["configurable"]["is_plan_mode"] is True
    assert pro["configurable"]["subagent_enabled"] is False
    assert pro["configurable"]["thinking_enabled"] is True
    assert pro["configurable"]["reasoning_effort"] == "medium"
    assert pro["configurable"]["max_tool_calls"] == 12
    ultra = prepare_xingxi_config(
        {
            "configurable": {
                "mode": "ultra",
                "thinking_enabled": False,
                "reasoning_effort": "minimal",
            }
        }
    )
    assert ultra["configurable"]["mode"] == "ultra"
    assert ultra["configurable"]["is_plan_mode"] is True
    assert ultra["configurable"]["subagent_enabled"] is False
    assert ultra["configurable"]["thinking_enabled"] is True
    assert ultra["configurable"]["reasoning_effort"] == "medium"
    assert ultra["configurable"]["max_tool_calls"] > pro["configurable"]["max_tool_calls"]


def test_ultra_keeps_domain_comparison_tool_without_generic_tools() -> None:
    from deerflow.agents.xingxi.tools import build_xingxi_tools

    assert [tool.name for tool in build_xingxi_tools(mode="ultra")] == [
        "search_sources",
        "query_knowledge_graph",
        "query_timeline",
        "query_map_features",
        "gloss_ancient_text",
        "resolve_name_variants",
        "compare_sources",
    ]
