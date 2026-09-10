from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import ValidationError
from wu_culture.citations import (
    AnswerCitation,
    CitationContract,
    EvidenceDetail,
    build_citation_contract,
    format_evidence_markdown_link,
    validate_answer_citations,
)
from wu_culture.citations.contract import evidence_detail_from_pack_item, evidence_detail_from_record
from wu_culture.evidence_pack import EvidencePackAssembler, EvidencePackConfig
from wu_culture.hybrid import HybridChannel, HybridSearchHit
from wu_culture.models import (
    AuthorizationStatus,
    AuthorizedUse,
    Citation,
    CopyrightStatus,
    Evidence,
    EvidenceRecord,
    ReviewStatus,
    SourceDocument,
    SourceDocumentStatus,
    SourceLevel,
    SourceType,
    TextChunk,
    VisibilityScope,
)

from deerflow.agents.middlewares.evidence_citation_middleware import EvidenceCitationMiddleware


def _hit(
    rank: int,
    *,
    document_id: str | None = None,
    evidence_id: str | None = None,
    quote: str | None = None,
) -> HybridSearchHit:
    document_id = document_id or f"doc-{rank}"
    return HybridSearchHit(
        release_id="release-1",
        chunk_id=f"chunk-{rank}",
        fused_score=1 / rank,
        channels=(HybridChannel.FULLTEXT,),
        citation=Citation(
            evidence_id=evidence_id or f"evidence-{rank}",
            document_id=document_id,
            source_file_id=f"file-{rank}",
            document_title="《木渎小志》",
            edition="民国铅印本",
            volume=f"卷{rank}",
            section="桥梁",
            page_start=10 + rank,
            page_end=10 + rank,
            folio_start=f"{rank}a",
            folio_end=f"{rank}b",
            quote=quote or f"香溪第{rank}桥记载。",
            source_level=SourceLevel.A,
            review_status=ReviewStatus.REVIEWED,
        ),
    )


def _pack():
    return EvidencePackAssembler(token_counter=len).assemble(
        (_hit(1), _hit(2, document_id="doc-2")),
        release_id="release-1",
        config=EvidencePackConfig(token_budget=5000),
    )


def test_contract_numbers_follow_pack_order_and_preserve_locators() -> None:
    pack = _pack()
    contract = build_citation_contract(pack)

    assert contract.schema_version == "answer-citation-v1"
    assert [c.number for c in contract.citations] == [1, 2]
    assert contract.citations[0].evidence_id == "evidence-1"
    assert contract.citations[0].document_title == "《木渎小志》"
    assert contract.citations[0].volume == "卷1"
    assert contract.citations[0].page_start == 11
    assert contract.citations[0].source_file_id == "file-1"
    assert contract.citations[0].folio_start == "1a"
    assert contract.citations[0].folio_end == "1b"
    assert contract.citations[0].href == "evidence://evidence-1"
    assert contract.citations[0].locator_label == "《木渎小志》 卷1 p.11"
    assert json.loads(contract.to_canonical_json()) == contract.model_dump(mode="json")
    assert contract.allowed_evidence_ids() == frozenset({"evidence-1", "evidence-2"})


def test_single_and_multi_citation_sentence_validation() -> None:
    pack = _pack()
    text = "香溪沿岸有古桥" + format_evidence_markdown_link(number=1, evidence_id="evidence-1") + format_evidence_markdown_link(number=2, evidence_id="evidence-2") + "。"
    result = validate_answer_citations(text, pack=pack)

    assert result.rejected == ()
    assert [ref.evidence_id for ref in result.valid_refs] == ["evidence-1", "evidence-2"]
    assert "evidence://evidence-1" in result.sanitized_text
    assert "evidence://evidence-2" in result.sanitized_text


def test_repeated_citation_keeps_stable_number() -> None:
    pack = _pack()
    text = f"甲说{format_evidence_markdown_link(number=9, evidence_id='evidence-1')}，乙说{format_evidence_markdown_link(number=9, evidence_id='evidence-1')}。"
    result = validate_answer_citations(text, pack=pack)

    assert result.rejected == ()
    assert result.sanitized_text.count("[citation:1](evidence://evidence-1)") == 2
    assert [ref.number for ref in result.valid_refs] == [1]


def test_unknown_evidence_id_is_dropped() -> None:
    pack = _pack()
    text = "可靠说法" + format_evidence_markdown_link(number=1, evidence_id="evidence-1") + "不可靠说法" + format_evidence_markdown_link(number=3, evidence_id="evidence-forged") + "。"
    result = validate_answer_citations(text, pack=pack)

    assert len(result.rejected) == 1
    assert result.rejected[0].claimed_evidence_id == "evidence-forged"
    assert "evidence-forged" not in result.sanitized_text
    assert "[citation:1](evidence://evidence-1)" in result.sanitized_text
    assert result.rewritten is True


def test_generic_evidence_markdown_is_normalized_to_citation_protocol() -> None:
    pack = _pack()
    text = "出处见[《木渎小志》](evidence://evidence-1)。"
    result = validate_answer_citations(text, pack=pack)
    assert result.rejected == ()
    assert "[citation:1](evidence://evidence-1)" in result.sanitized_text


def test_no_pack_context_strips_all_evidence_links() -> None:
    text = "伪证" + format_evidence_markdown_link(number=1, evidence_id="evidence-1")
    result = validate_answer_citations(text)
    assert "evidence://" not in result.sanitized_text
    assert result.rejected


def test_answer_citation_rejects_non_evidence_href() -> None:
    with pytest.raises(ValidationError):
        AnswerCitation(
            number=1,
            evidence_id="evidence-1",
            chunk_id="chunk-1",
            document_id="doc-1",
            document_title="书",
            page_start=1,
            page_end=1,
            quote="原文",
            source_level="A",
            review_status="reviewed",
            href="https://example.com/x",
        )


def test_contract_rejects_duplicate_evidence_ids() -> None:
    cite = AnswerCitation(
        number=1,
        evidence_id="evidence-1",
        chunk_id="chunk-1",
        document_id="doc-1",
        document_title="书",
        page_start=1,
        page_end=1,
        quote="原文",
        source_level="A",
        review_status="reviewed",
        href="evidence://evidence-1",
    )
    with pytest.raises(ValidationError):
        CitationContract(
            release_id="r1",
            citations=(
                cite,
                cite.model_copy(update={"number": 2, "chunk_id": "chunk-2"}),
            ),
        )


def test_evidence_detail_from_pack_and_record_match_db_locators() -> None:
    pack = _pack()
    detail = evidence_detail_from_pack_item(pack.items[0])
    assert detail.href == "evidence://evidence-1"
    assert detail.document_title == "《木渎小志》"
    assert detail.volume == "卷1"
    assert detail.page_start == 11
    assert detail.source_file_id == "file-1"
    assert detail.folio_start == "1a"
    assert detail.folio_end == "1b"

    with pytest.raises(ValidationError, match="href evidence id"):
        EvidenceDetail.model_validate(detail.model_dump(mode="json") | {"href": "evidence://other"})

    record = EvidenceRecord(
        document=SourceDocument(
            id="doc-1",
            title="《木渎小志》",
            edition="民国铅印本",
            source_type=SourceType.GAZETTEER,
            source_level=SourceLevel.A,
            copyright_status=CopyrightStatus.PUBLIC_DOMAIN,
            source_institution="木渎地方志办",
            holder="木渎地方志办",
            status=SourceDocumentStatus.REGISTERED,
            authorization_status=AuthorizationStatus.ACTIVE,
            authorization_basis="公版",
            visibility_scope=VisibilityScope.PUBLIC,
            authorized_uses=(AuthorizedUse.PUBLIC_QUOTE,),
        ),
        chunk=TextChunk(
            id="chunk-1",
            document_id="doc-1",
            volume="卷一",
            section="桥梁",
            paragraph="1",
            original_text="香溪第一桥记载。",
            normalized_text="香溪第一桥记载。",
            page_start=12,
            page_end=12,
            review_status=ReviewStatus.REVIEWED,
        ),
        evidence=Evidence(
            id="evidence-1",
            document_id="doc-1",
            chunk_id="chunk-1",
            quote="香溪第一桥记载。",
            source_level=SourceLevel.A,
            review_status=ReviewStatus.REVIEWED,
        ),
    )
    from_db = evidence_detail_from_record(record)
    assert from_db.page_start == 12
    assert from_db.volume == "卷一"
    assert from_db.document_title == "《木渎小志》"
    assert from_db.href == "evidence://evidence-1"


def test_middleware_rewrites_final_ai_message_using_tool_evidence_pack() -> None:
    pack = _pack()
    tool_payload = {
        "status": "supported",
        "evidence_pack": pack.model_dump(mode="json"),
        "hits": [],
    }
    state = {
        "messages": [
            ToolMessage(content=json.dumps(tool_payload, ensure_ascii=False), tool_call_id="t1"),
            AIMessage(content=("桥见记载" + format_evidence_markdown_link(number=7, evidence_id="evidence-1") + "，并有伪证" + format_evidence_markdown_link(number=8, evidence_id="missing-id") + "。")),
        ]
    }

    update = EvidenceCitationMiddleware().after_model(state, runtime=object())  # type: ignore[arg-type]

    assert update is not None
    message = update["messages"][0]
    assert isinstance(message, AIMessage)
    assert "[citation:1](evidence://evidence-1)" in message.content
    assert "missing-id" not in message.content
    assert message.response_metadata["citation_validation"]["rejected_count"] == 1
