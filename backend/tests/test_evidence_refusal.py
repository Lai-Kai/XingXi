from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from wu_culture.evidence_pack import EvidencePack, EvidencePackItem, EvidencePackStatus
from wu_culture.models import ReviewStatus, SourceLevel
from wu_culture.refusal import (
    REFUSAL_CANONICAL_MESSAGE,
    evaluate_refusal,
    is_historical_nonexistence_claim,
)

from deerflow.agents.middlewares.evidence_refusal_middleware import EvidenceRefusalMiddleware


def _item(*, evidence_id: str, level: SourceLevel, quote: str) -> EvidencePackItem:
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
        review_status=ReviewStatus.REVIEWED,
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
    assert "补充分析（以下内容未被当前本地文献核验）" in content
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
    assert "暂无经复核的明确记载" in content
    assert "补充分析" in content
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
