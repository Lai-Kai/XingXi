from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from wu_culture.evidence_pack import EvidencePack, EvidencePackItem, EvidencePackStatus
from wu_culture.models import ReviewStatus, SourceLevel
from wu_culture.refusal import (
    REFUSAL_CANONICAL_MESSAGE,
    evaluate_refusal,
    is_historical_nonexistence_claim,
)

from deerflow.agents.middlewares.evidence_refusal_middleware import EvidenceRefusalMiddleware


def _item(*, evidence_id: str, level: SourceLevel, quote: str, review_status: ReviewStatus = ReviewStatus.REVIEWED) -> EvidencePackItem:
    return EvidencePackItem(
        rank=1,
        evidence_id=evidence_id,
        chunk_id=f"chunk-{evidence_id}",
        document_id=f"doc-{evidence_id}",
        document_title="《木渎小志》",
        edition="民国铅印本",
        volume="卷一",
        section="桥梁",
        page_start=12,
        page_end=12,
        quote=quote,
        quote_provenance="verbatim",
        quote_truncated=False,
        original_quote_chars=len(quote),
        original_quote_sha256="a" * 64,
        source_level=level,
        review_status=review_status,
    )


def test_empty_results_refuse_without_historical_nonexistence() -> None:
    pack = EvidencePack(
        release_id="release-1",
        status=EvidencePackStatus.EMPTY,
        token_budget=4000,
        used_tokens=0,
        input_count=0,
        deduplicated_count=0,
        omitted_count=0,
        document_count=0,
        items=(),
    )
    result = evaluate_refusal(query="香溪沿岸有哪些古桥", search_status="insufficient", pack=pack)

    assert result.decision.should_refuse is True
    assert REFUSAL_CANONICAL_MESSAGE in result.text
    assert "不等于历史上不存在" in result.text
    assert "历史上不存在" not in result.text.replace("不等于历史上不存在", "")


def test_low_grade_only_materials_are_refused_as_confirmed_history() -> None:
    pack = EvidencePack(
        release_id="release-1",
        status=EvidencePackStatus.READY,
        token_budget=4000,
        used_tokens=100,
        input_count=1,
        deduplicated_count=0,
        omitted_count=0,
        document_count=1,
        items=(_item(evidence_id="e-d", level=SourceLevel.D, quote="民间传说丙桥很灵验"),),
    )
    result = evaluate_refusal(query="丙桥传说", search_status="inferred", pack=pack)

    assert result.decision.should_refuse is True
    assert result.decision.reason.value == "low_grade_only"


def test_mismatched_evidence_is_refused() -> None:
    pack = EvidencePack(
        release_id="release-1",
        status=EvidencePackStatus.READY,
        token_budget=4000,
        used_tokens=100,
        input_count=1,
        deduplicated_count=0,
        omitted_count=0,
        document_count=1,
        items=(_item(evidence_id="e-a", level=SourceLevel.A, quote="某寺钟声远播"),),
    )
    result = evaluate_refusal(query="香溪沿岸有哪些古桥", search_status="supported", pack=pack)

    assert result.decision.should_refuse is True
    assert result.decision.reason.value == "evidence_mismatch"


def test_matching_supported_evidence_is_not_refused() -> None:
    pack = EvidencePack(
        release_id="release-1",
        status=EvidencePackStatus.READY,
        token_budget=4000,
        used_tokens=100,
        input_count=1,
        deduplicated_count=0,
        omitted_count=0,
        document_count=1,
        items=(_item(evidence_id="e-a", level=SourceLevel.A, quote="香溪沿岸有普济桥与如意桥"),),
    )
    result = evaluate_refusal(query="香溪沿岸有哪些古桥", search_status="supported", pack=pack)

    assert result.decision.should_refuse is False
    assert result.text == ""


def test_supported_status_without_evidence_pack_is_refused() -> None:
    result = evaluate_refusal(
        query="香溪沿岸有哪些古桥",
        search_status="supported",
        pack=None,
    )

    assert result.decision.should_refuse is True
    assert result.decision.reason.value == "insufficient_pack"
    assert REFUSAL_CANONICAL_MESSAGE in result.text


def test_nonexistence_claim_detector() -> None:
    assert is_historical_nonexistence_claim("因此历史上不存在该桥") is True
    assert is_historical_nonexistence_claim("当前检索范围内暂无明确记载") is False


def test_middleware_replaces_unsupported_answer() -> None:
    tool_payload = {
        "status": "insufficient",
        "evidence_pack": {
            "schema_version": "evidence-pack-v1",
            "release_id": "release-1",
            "status": "empty",
            "token_budget": 4000,
            "used_tokens": 0,
            "input_count": 0,
            "deduplicated_count": 0,
            "omitted_count": 0,
            "document_count": 0,
            "items": [],
        },
        "hits": [],
        "message": "暂无明确方志记载",
    }
    state = {
        "messages": [
            HumanMessage(content="香溪沿岸有哪些古桥？"),
            ToolMessage(content=json.dumps(tool_payload, ensure_ascii=False), tool_call_id="t1"),
            AIMessage(content="根据资料，香溪沿岸历史上不存在任何桥梁。"),
        ]
    }

    update = EvidenceRefusalMiddleware().after_model(state, runtime=object())  # type: ignore[arg-type]

    assert update is not None
    content = update["messages"][0].content
    assert REFUSAL_CANONICAL_MESSAGE in content
    assert "历史上不存在任何桥梁" not in content
    assert update["messages"][0].response_metadata["refusal_validation"]["should_refuse"] is True


def test_middleware_preserves_inline_reasoning_when_replacing_answer() -> None:
    tool_payload = {
        "status": "insufficient",
        "evidence_pack": {
            "schema_version": "evidence-pack-v1",
            "release_id": "release-1",
            "status": "empty",
            "token_budget": 4000,
            "used_tokens": 0,
            "input_count": 0,
            "deduplicated_count": 0,
            "omitted_count": 0,
            "document_count": 0,
            "items": [],
        },
        "hits": [],
    }
    state = {
        "messages": [
            HumanMessage(content="香溪沿岸有哪些古桥？"),
            ToolMessage(content=json.dumps(tool_payload, ensure_ascii=False), tool_call_id="t1"),
            AIMessage(content="<think>先检查资料中的地点和桥梁记载。</think>根据资料，香溪沿岸历史上不存在任何桥梁。"),
        ]
    }

    update = EvidenceRefusalMiddleware().after_model(state, runtime=object())  # type: ignore[arg-type]

    assert update is not None
    message = update["messages"][0]
    assert REFUSAL_CANONICAL_MESSAGE in message.content
    assert message.additional_kwargs["reasoning_content"] == "先检查资料中的地点和桥梁记载。"


def test_middleware_keeps_model_analysis_as_unverified_supplement() -> None:
    tool_payload = {
        "status": "insufficient",
        "evidence_pack": {
            "schema_version": "evidence-pack-v1",
            "release_id": "release-1",
            "status": "empty",
            "token_budget": 4000,
            "used_tokens": 0,
            "input_count": 0,
            "deduplicated_count": 0,
            "omitted_count": 0,
            "document_count": 0,
            "items": [],
        },
        "hits": [],
    }
    analysis = "从现有地名沿革和区域背景看，该地点可能与古代水系变迁有关，但仍需扩大文献范围核验。"
    state = {
        "messages": [
            HumanMessage(content="这个地点的历史背景是什么？"),
            ToolMessage(content=json.dumps(tool_payload, ensure_ascii=False), tool_call_id="t1"),
            AIMessage(content=analysis),
        ]
    }

    update = EvidenceRefusalMiddleware().after_model(state, runtime=object())  # type: ignore[arg-type]

    assert update is not None
    content = update["messages"][0].content
    assert REFUSAL_CANONICAL_MESSAGE in content
    assert content.startswith(analysis)
    assert "本地资料核验" in content
    assert "背景说明或待核验分析" in content
    assert analysis in content


def test_middleware_keeps_model_answer_when_only_low_grade_material_exists() -> None:
    tool_payload = {
        "status": "inferred",
        "evidence_pack": {
            "schema_version": "evidence-pack-v1",
            "release_id": "release-1",
            "status": "ready",
            "token_budget": 4000,
            "used_tokens": 100,
            "input_count": 1,
            "deduplicated_count": 0,
            "omitted_count": 0,
            "document_count": 1,
            "items": [
                _item(evidence_id="e-d", level=SourceLevel.D, quote="木渎旧有桥梁").model_dump(mode="json"),
            ],
        },
        "hits": [],
    }
    analysis = "这条材料提示该地曾有桥梁活动，但年代和具体位置还需要复核。"
    state = {
        "messages": [
            HumanMessage(content="木渎有哪些桥梁？"),
            ToolMessage(content=json.dumps(tool_payload, ensure_ascii=False), tool_call_id="t1"),
            AIMessage(content=analysis),
        ]
    }

    update = EvidenceRefusalMiddleware().after_model(state, runtime=object())  # type: ignore[arg-type]

    assert update is not None
    content = update["messages"][0].content
    assert content.startswith(analysis)
    assert "暂无经复核的明确记载" not in content
    assert REFUSAL_CANONICAL_MESSAGE not in content
    assert "D/E 级" in content
    assert analysis in content
    assert update["messages"][0].response_metadata["refusal_validation"]["reason"] == "low_grade_only"


def test_middleware_aggregates_multiple_search_results_before_refusing() -> None:
    supported_payload = {
        "status": "supported",
        "evidence_pack": EvidencePack(
            release_id="release-1",
            status=EvidencePackStatus.READY,
            token_budget=4000,
            used_tokens=100,
            input_count=1,
            deduplicated_count=0,
            omitted_count=0,
            document_count=1,
            items=(_item(evidence_id="e-a", level=SourceLevel.A, quote="香溪沿岸有普济桥"),),
        ).model_dump(mode="json"),
        "hits": [],
    }
    empty_payload = {
        "status": "insufficient",
        "evidence_pack": EvidencePack(
            release_id="release-1",
            status=EvidencePackStatus.EMPTY,
            token_budget=4000,
            used_tokens=0,
            input_count=0,
            deduplicated_count=0,
            omitted_count=0,
            document_count=0,
            items=(),
        ).model_dump(mode="json"),
        "hits": [],
    }
    state = {
        "messages": [
            HumanMessage(content="香溪沿岸有哪些古桥？"),
            ToolMessage(content=json.dumps(supported_payload, ensure_ascii=False), tool_call_id="t1"),
            ToolMessage(content=json.dumps(empty_payload, ensure_ascii=False), tool_call_id="t2"),
            AIMessage(content="香溪沿岸有普济桥。"),
        ]
    }

    update = EvidenceRefusalMiddleware().after_model(state, runtime=object())  # type: ignore[arg-type]

    assert update is None


def test_removing_all_evidence_forces_refusal() -> None:
    supported = EvidencePack(
        release_id="release-1",
        status=EvidencePackStatus.READY,
        token_budget=4000,
        used_tokens=100,
        input_count=1,
        deduplicated_count=0,
        omitted_count=0,
        document_count=1,
        items=(_item(evidence_id="e-a", level=SourceLevel.A, quote="香溪沿岸有普济桥与如意桥"),),
    )
    assert evaluate_refusal(query="香溪沿岸有哪些古桥", search_status="supported", pack=supported).decision.should_refuse is False

    removed = EvidencePack(
        release_id="release-1",
        status=EvidencePackStatus.EMPTY,
        token_budget=4000,
        used_tokens=0,
        input_count=0,
        deduplicated_count=0,
        omitted_count=0,
        document_count=0,
        items=(),
    )
    refused = evaluate_refusal(query="香溪沿岸有哪些古桥", search_status="insufficient", pack=removed)
    assert refused.decision.should_refuse is True
    assert REFUSAL_CANONICAL_MESSAGE in refused.text
    assert "检索范围" in refused.text
    assert "可继续查找" in refused.text


def test_budget_exhausted_empty_pack_is_refused() -> None:
    pack = EvidencePack(
        release_id="release-1",
        status=EvidencePackStatus.INSUFFICIENT_BUDGET,
        token_budget=32,
        used_tokens=0,
        input_count=1,
        deduplicated_count=0,
        omitted_count=1,
        document_count=0,
        items=(),
    )
    result = evaluate_refusal(query="香溪古桥", search_status="supported", pack=pack)
    assert result.decision.should_refuse is True
    assert result.decision.reason.value == "budget_exhausted"


def _retrieved(items: tuple[EvidencePackItem, ...]) -> ToolMessage:
    pack = EvidencePack(
        release_id="release-1",
        status=EvidencePackStatus.READY if items else EvidencePackStatus.EMPTY,
        token_budget=4000,
        used_tokens=100 if items else 0,
        input_count=len(items),
        deduplicated_count=0,
        omitted_count=0,
        document_count=len({item.document_id for item in items}),
        items=items,
    )
    return ToolMessage(
        content=json.dumps({"status": "supported" if items else "insufficient", "evidence_pack": pack.model_dump(mode="json"), "hits": []}, ensure_ascii=False),
        tool_call_id="search-1",
    )


@pytest.mark.parametrize(
    ("level", "review_status", "expected_note", "absent_note"),
    [
        (SourceLevel.U, ReviewStatus.REVIEWED, "尚未评级", "待复核"),
        (SourceLevel.U, ReviewStatus.PENDING, "尚未评级", "D/E 级"),
        (SourceLevel.A, ReviewStatus.PENDING, "待复核", "尚未评级"),
        (SourceLevel.C, ReviewStatus.DISPUTED, "存在争议", "待复核"),
    ],
)
def test_matched_material_answers_first_with_accurate_quality_note(level, review_status, expected_note, absent_note) -> None:
    item = _item(evidence_id="e-local", level=level, review_status=review_status, quote="木渎旧有普济桥。")
    answer = "《木渎小志》记载木渎有普济桥。[citation:1](evidence://e-local)"
    update = EvidenceRefusalMiddleware().after_model(
        {"messages": [HumanMessage(content="木渎有哪些桥梁？"), _retrieved((item,)), AIMessage(content=answer, id="answer-1")]},
        runtime=object(),  # type: ignore[arg-type]
    )

    assert update is not None
    updated = update["messages"][0]
    assert updated.content.startswith(answer)
    assert updated.id == "answer-1"
    assert expected_note in updated.content
    assert absent_note not in updated.content
    assert "暂无" not in updated.content
    assert updated.response_metadata["refusal_validation"]["should_refuse"] is False
    assert item.source_level == level
    assert item.review_status == review_status


def test_mixed_sources_do_not_describe_all_material_as_unreviewed() -> None:
    items = (
        _item(evidence_id="e-a", level=SourceLevel.A, quote="木渎旧有普济桥。"),
        _item(evidence_id="e-u", level=SourceLevel.U, review_status=ReviewStatus.PENDING, quote="木渎旧有普济桥。").model_copy(update={"rank": 2}),
    )
    answer = "木渎地方文献记载了普济桥。"
    update = EvidenceRefusalMiddleware().after_model(
        {"messages": [HumanMessage(content="木渎有哪些桥梁？"), _retrieved(items), AIMessage(content=answer)]},
        runtime=object(),  # type: ignore[arg-type]
    )
    assert update is not None
    content = update["messages"][0].content
    assert content.startswith(answer)
    assert "部分来源尚未评级" in content
    assert "部分引用片段待复核" in content
    assert "均为" not in content
    assert "暂无" not in content


def test_empty_current_turn_cannot_reuse_old_turn_evidence() -> None:
    old_item = _item(evidence_id="e-old", level=SourceLevel.A, quote="木渎旧有普济桥。")
    answer = "园林沿革通常可以从营建者、修缮年代和空间格局三个方面了解。"
    update = EvidenceRefusalMiddleware().after_model(
        {
            "messages": [
                HumanMessage(content="木渎有哪些桥梁？"),
                _retrieved((old_item,)),
                AIMessage(content="旧志记载普济桥。"),
                HumanMessage(content="木渎园林的沿革呢？"),
                _retrieved(()),
                AIMessage(content=answer),
            ]
        },
        runtime=object(),  # type: ignore[arg-type]
    )
    assert update is not None
    updated = update["messages"][0]
    assert updated.content.startswith(answer)
    assert REFUSAL_CANONICAL_MESSAGE in updated.content
    assert updated.response_metadata["refusal_validation"]["reason"] == "empty_results"


def test_unrated_unrelated_evidence_is_still_a_miss() -> None:
    payload = _retrieved((_item(evidence_id="e-u", level=SourceLevel.U, quote="某寺钟声远播。"),))
    pack = EvidencePack.model_validate(json.loads(payload.content)["evidence_pack"])
    result = evaluate_refusal(query="香溪沿岸有哪些古桥", search_status="inferred", pack=pack, allow_inferred_answer=True)
    assert result.decision.should_refuse is True
    assert result.decision.reason.value == "evidence_mismatch"


def test_daily_topic_uses_verified_query_instead_of_prompt_instructions() -> None:
    item = _item(evidence_id="e-topic", level=SourceLevel.U, quote="越王献西施于此山。")
    tool_message = _retrieved((item,))
    payload = json.loads(tool_message.content)
    payload.update({"resolved_query": "西施", "attached_daily_topic_evidence": True})
    tool_message.content = json.dumps(payload, ensure_ascii=False)
    answer = "这份文献记载了越王献西施的故事。[citation:1](evidence://e-topic)"
    update = EvidenceRefusalMiddleware().after_model(
        {"messages": [HumanMessage(content="请介绍西施在江南活动的故事，并标明文献出处。"), tool_message, AIMessage(content=answer)]},
        runtime=object(),  # type: ignore[arg-type]
    )
    assert update is not None
    assert update["messages"][0].content.startswith(answer)
    assert REFUSAL_CANONICAL_MESSAGE not in update["messages"][0].content
    assert update["messages"][0].response_metadata["refusal_validation"]["should_refuse"] is False


def test_unused_unrated_candidates_do_not_downgrade_a_reviewed_citation() -> None:
    items = (
        _item(evidence_id="e-a", level=SourceLevel.A, quote="木渎旧有普济桥。"),
        _item(evidence_id="e-u", level=SourceLevel.U, review_status=ReviewStatus.PENDING, quote="木渎旧有普济桥。").model_copy(update={"rank": 2}),
    )
    answer = "旧志记载木渎有普济桥。[citation:1](evidence://e-a)"
    update = EvidenceRefusalMiddleware().after_model(
        {"messages": [HumanMessage(content="木渎有哪些桥梁？"), _retrieved(items), AIMessage(content=answer)]},
        runtime=object(),  # type: ignore[arg-type]
    )
    assert update is None


@pytest.mark.parametrize("include_reasoning", [False, True])
def test_quality_note_preserves_answer_blocks_once_without_exposing_reasoning(include_reasoning: bool) -> None:
    item = _item(evidence_id="e-u", level=SourceLevel.U, quote="木渎旧有普济桥。")
    parts = [
        {"type": "text", "text": "旧志记载木渎有普济桥。[citation:1](evidence://e-u)"},
        {"type": "text", "text": "相关沿革仍可结合其他材料继续考证。"},
    ]
    if include_reasoning:
        parts.insert(0, {"type": "reasoning", "summary": [{"type": "summary_text", "text": "private-reasoning"}]})
    update = EvidenceRefusalMiddleware().after_model(
        {"messages": [HumanMessage(content="木渎有哪些桥梁？"), _retrieved((item,)), AIMessage(content=parts)]},
        runtime=object(),  # type: ignore[arg-type]
    )
    assert update is not None
    visible = "\n".join(part["text"] for part in update["messages"][0].content if part.get("type") == "text")
    assert visible.count("旧志记载木渎有普济桥。") == 1
    assert visible.count("相关沿革仍可结合其他材料继续考证。") == 1
    assert "evidence://e-u" in visible
    assert "尚未评级" in visible
    assert "private-reasoning" not in visible


@pytest.mark.parametrize("with_evidence", [False, True])
def test_xishi_reliability_method_answer_survives_product_middleware_chain(with_evidence: bool) -> None:
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel

    from deerflow.agents.middlewares.evidence_citation_middleware import EvidenceCitationMiddleware

    item = _item(evidence_id="e-xishi", level=SourceLevel.U, review_status=ReviewStatus.PENDING, quote="越王献西施于此山，或曰旧说。")
    tool_message = _retrieved((item,) if with_evidence else ())
    if with_evidence:
        payload = json.loads(tool_message.content)
        payload.update({"attached_daily_topic_evidence": True, "resolved_query": "西施"})
        tool_message.content = json.dumps(payload, ensure_ascii=False)
    method = "先核对成书年代、版本和原文措辞，再判断各书是否相互抄引，最后比较独立文献与实物证据。地方传说的流传不能直接证明人物亲历。"
    example = "该段保存了西施的地方叙事。[citation:1](evidence://e-xishi)" if with_evidence else "没有本地材料时，也可以先用这些步骤逐项核查。"
    model = FakeMessagesListChatModel(responses=[AIMessage(content=[{"type": "reasoning", "summary": []}, {"type": "text", "text": method}, {"type": "text", "text": example}])])
    agent = create_agent(model=model, middleware=[EvidenceCitationMiddleware(), EvidenceRefusalMiddleware()])
    result = agent.invoke(
        {
            "messages": [
                HumanMessage(content="怎样判断地方文献中西施与吴地联系的记载是否可靠？"),
                AIMessage(content="", tool_calls=[{"name": "search_sources", "args": {"query": "西施"}, "id": "search-1"}]),
                tool_message,
            ]
        }
    )

    final = result["messages"][-1]
    visible = "\n".join(block["text"] for block in final.content if block.get("type") == "text")
    assert visible.startswith(method)
    assert visible.count(method) == 1
    assert visible.count(example) == 1
    assert "暂无经复核的明确记载" not in visible
    if with_evidence:
        assert "本地资料核验" not in visible
        assert "来源尚未评级；引用片段待复核" in visible
    else:
        assert "本地资料核验" in visible
        assert "evidence://" not in visible
