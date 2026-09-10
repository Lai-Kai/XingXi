from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime
from pydantic import ValidationError
from wu_culture import EvidenceSearchService, InMemoryEvidenceRepository
from wu_culture.fulltext import FullTextSearchRequest, build_highlighted_snippet, parse_fulltext_query, score_fulltext_match

from deerflow.agents.xingxi.tools import _active_release_context, _release_id_from_runtime, _release_scope_from_runtime, build_search_sources_tool


def test_query_parser_preserves_phrases_and_sanitizes_special_characters() -> None:
    parsed = parse_fulltext_query('"香溪沿岸" 木渎 OR %_（旧名）')

    assert parsed.phrases == ("香溪沿岸",)
    assert parsed.terms == ("木渎", "or", "旧名")
    assert parsed.all_terms == ("香溪沿岸", "木渎", "or", "旧名")


def test_unspaced_chinese_query_is_an_exact_phrase() -> None:
    parsed = parse_fulltext_query("香溪沿岸古桥")

    assert parsed.phrases == ("香溪沿岸古桥",)
    assert parsed.terms == ()


def test_natural_language_chinese_question_keeps_recall_terms() -> None:
    parsed = parse_fulltext_query("闔閭建了什么")

    assert parsed.phrases == ()
    assert "闔閭" in parsed.terms
    assert "什么" not in parsed.terms


def test_highlighted_summary_centres_first_match_without_html() -> None:
    text = "卷一记载木渎镇沿香溪分布多座古桥，其中虹饮山房附近尤详。"

    snippet = build_highlighted_snippet(text, ("香溪", "古桥"), max_characters=24)

    assert "【香溪】" in snippet
    assert "【古桥】" in snippet
    assert "<mark>" not in snippet
    assert len(snippet) <= 30


def test_proper_noun_fields_have_deterministic_weight() -> None:
    title_score = score_fulltext_match(
        title="木渎小志",
        headings="卷一 桥梁",
        body="香溪沿岸有虹桥。",
        phrases=(),
        terms=("木渎",),
    )
    body_score = score_fulltext_match(
        title="吴县志",
        headings="卷一 桥梁",
        body="木渎香溪沿岸有虹桥。",
        phrases=(),
        terms=("木渎",),
    )

    assert title_score > body_score


def test_request_rejects_unbounded_pagination() -> None:
    with pytest.raises(ValidationError):
        FullTextSearchRequest(query="木渎", page=0, page_size=20)
    with pytest.raises(ValidationError):
        FullTextSearchRequest(query="木渎", page=1, page_size=101)


def test_tool_resolves_release_frozen_in_run_metadata() -> None:
    runtime = SimpleNamespace(config={"metadata": {"knowledge_release_id": "release-v1"}})

    assert _release_id_from_runtime(runtime) == "release-v1"


def test_tool_prefers_server_owned_release_runtime_context() -> None:
    runtime = SimpleNamespace(
        context={"knowledge_release_id": "release-internal", "knowledge_release_scope": "internal"},
        config={"metadata": {"knowledge_release_id": "release-public", "knowledge_release_scope": "public"}},
    )

    assert _release_id_from_runtime(runtime) == "release-internal"
    assert _release_scope_from_runtime(runtime) == "internal"


@pytest.mark.asyncio
async def test_tool_uses_active_internal_release_when_runtime_has_no_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Release:
        id = "release-internal"
        scope = "internal"

    class _Repository:
        async def get_active_summary(self):
            return _Release()

    class _Engine:
        @staticmethod
        def get_session_factory():
            return object()

    import deerflow.persistence.engine as persistence_engine

    monkeypatch.setattr(persistence_engine, "get_session_factory", _Engine.get_session_factory)
    monkeypatch.setattr(
        "deerflow.persistence.wu_culture.SqlKnowledgeReleaseRepository",
        lambda _session_factory: _Repository(),
    )

    assert await _active_release_context(None) == ("release-internal", "internal")


@pytest.mark.asyncio
async def test_search_tool_receives_release_context_through_tool_node() -> None:
    tool = build_search_sources_tool(
        search_service=EvidenceSearchService(InMemoryEvidenceRepository()),
    )
    node = ToolNode([tool])
    tool_call = {
        "name": "search_sources",
        "args": {"query": "木渎镇", "top_k": 3},
        "id": "search-1",
        "type": "tool_call",
    }
    config = {
        "configurable": {
            "thread_id": "thread-1",
            "__pregel_runtime": Runtime(
                context={
                    "knowledge_release_id": "release-internal",
                    "knowledge_release_scope": "internal",
                }
            ),
        }
    }

    result = await node.ainvoke(
        {"messages": [AIMessage(content="", tool_calls=[tool_call])]},
        config=config,
    )

    payload = json.loads(result["messages"][0].content)
    assert payload["release_id"] == "release-internal"
