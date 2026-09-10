from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import ValidationError
from wu_culture.evidence_pack import (
    EvidencePackAssembler,
    EvidencePackConfig,
    EvidencePackStatus,
)
from wu_culture.hybrid import HybridChannel, HybridSearchHit
from wu_culture.models import Citation, ReviewStatus, SourceLevel


def _hit(
    rank: int,
    *,
    document_id: str | None = None,
    quote: str | None = None,
    evidence_id: str | None = None,
    title: str | None = None,
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
            document_title=title or f"《木渎志》卷{rank}",
            edition="清刻本完整版本说明",
            volume=f"卷{rank}",
            section="桥梁",
            page_start=rank,
            page_end=rank + 1,
            quote=quote or f"第{rank}条关于香溪桥梁的原文记载。",
            source_level=SourceLevel.A,
            review_status=ReviewStatus.REVIEWED,
        ),
    )


def _char_tokens(text: str) -> int:
    return len(text)


def test_small_pack_preserves_rank_metadata_and_stable_schema() -> None:
    pack = EvidencePackAssembler(token_counter=_char_tokens).assemble(
        (_hit(1), _hit(2)),
        release_id="release-1",
        config=EvidencePackConfig(token_budget=5000),
    )

    assert pack.status is EvidencePackStatus.READY
    assert [item.rank for item in pack.items] == [1, 2]
    assert pack.items[0].document_title == "《木渎志》卷1"
    assert pack.items[0].edition == "清刻本完整版本说明"
    assert pack.items[0].volume == "卷1"
    assert pack.items[0].page_start == 1
    assert pack.items[0].page_end == 2
    assert pack.items[0].source_level is SourceLevel.A
    assert pack.items[0].review_status is ReviewStatus.REVIEWED
    assert pack.items[0].quote_provenance == "verbatim"
    assert pack.schema_version == "evidence-pack-v1"
    assert json.loads(pack.to_canonical_json()) == pack.model_dump(mode="json")
    assert pack.to_canonical_json() == pack.to_canonical_json()
    assert pack.allowed_evidence_ids() == frozenset({"evidence-1", "evidence-2"})


def test_duplicate_evidence_and_chunk_are_removed() -> None:
    duplicate_evidence = _hit(2, evidence_id="evidence-1")
    duplicate_chunk = _hit(3).model_copy(update={"chunk_id": "chunk-1"})
    pack = EvidencePackAssembler(token_counter=_char_tokens).assemble(
        (_hit(1), duplicate_evidence, duplicate_chunk, _hit(4)),
        release_id="release-1",
        config=EvidencePackConfig(token_budget=5000),
    )

    assert [item.evidence_id for item in pack.items] == ["evidence-1", "evidence-4"]
    assert pack.deduplicated_count == 2


def test_identical_quote_is_deduplicated_only_within_same_document() -> None:
    first = _hit(1, document_id="doc-a", quote="香溪  古桥\n有记载")
    same_document = _hit(2, document_id="doc-a", quote="香溪 古桥 有记载")
    corroborating_document = _hit(3, document_id="doc-b", quote="香溪 古桥 有记载")
    pack = EvidencePackAssembler(token_counter=_char_tokens).assemble(
        (first, same_document, corroborating_document),
        release_id="release-1",
        config=EvidencePackConfig(token_budget=5000),
    )

    assert [item.evidence_id for item in pack.items] == ["evidence-1", "evidence-3"]
    assert pack.deduplicated_count == 1


def test_cross_document_coverage_precedes_repeated_document() -> None:
    hits = (
        _hit(1, document_id="doc-a"),
        _hit(2, document_id="doc-a"),
        _hit(3, document_id="doc-b"),
    )
    pack = EvidencePackAssembler(token_counter=_char_tokens).assemble(
        hits,
        release_id="release-1",
        config=EvidencePackConfig(token_budget=5000, max_items=2),
    )

    assert [(item.rank, item.document_id) for item in pack.items] == [(1, "doc-a"), (3, "doc-b")]
    assert pack.document_count == 2


def test_oversized_first_quote_reserves_room_for_another_document() -> None:
    hits = (
        _hit(1, document_id="doc-a", quote="甲" * 2000),
        _hit(2, document_id="doc-b", quote="乙" * 20),
    )
    pack = EvidencePackAssembler(token_counter=_char_tokens).assemble(
        hits,
        release_id="release-1",
        config=EvidencePackConfig(
            token_budget=1100,
            max_items=2,
            max_quote_tokens=1000,
            min_quote_tokens=8,
        ),
    )

    assert [item.document_id for item in pack.items] == ["doc-a", "doc-b"]
    assert pack.items[0].quote_truncated is True
    assert pack.document_count == 2


def test_oversized_quote_is_only_field_truncated_and_traceable() -> None:
    original = "木渎香溪古桥原文" * 200
    pack = EvidencePackAssembler(token_counter=_char_tokens).assemble(
        (_hit(1, quote=original),),
        release_id="release-1",
        config=EvidencePackConfig(token_budget=650, max_quote_tokens=1000, min_quote_tokens=8),
    )

    assert pack.status is EvidencePackStatus.READY
    item = pack.items[0]
    assert item.quote_truncated is True
    assert item.quote != original
    assert original.startswith(item.quote.removesuffix("…"))
    assert item.original_quote_sha256 == hashlib.sha256(original.encode("utf-8")).hexdigest()
    assert item.document_title == "《木渎志》卷1"
    assert item.edition == "清刻本完整版本说明"
    assert item.volume == "卷1"
    assert item.page_end == 2
    assert pack.used_tokens <= pack.token_budget


def test_budget_too_small_for_metadata_returns_structured_result() -> None:
    pack = EvidencePackAssembler(token_counter=_char_tokens).assemble(
        (_hit(1),),
        release_id="release-1",
        config=EvidencePackConfig(token_budget=32, min_quote_tokens=8),
    )

    assert pack.status is EvidencePackStatus.INSUFFICIENT_BUDGET
    assert pack.items == ()
    assert pack.omitted_count == 1
    assert pack.used_tokens <= pack.token_budget


def test_empty_candidates_return_empty_pack() -> None:
    pack = EvidencePackAssembler(token_counter=_char_tokens).assemble(
        (),
        release_id="release-1",
        config=EvidencePackConfig(token_budget=200),
    )

    assert pack.status is EvidencePackStatus.EMPTY
    assert pack.items == ()


def test_pack_never_emits_model_generated_quote_text() -> None:
    original = "方志原文：香溪有普济桥。"
    pack = EvidencePackAssembler(token_counter=_char_tokens).assemble(
        (_hit(1, quote=original),),
        release_id="release-1",
        config=EvidencePackConfig(token_budget=5000),
    )
    assert pack.items[0].quote == original
    assert pack.items[0].quote_provenance == "verbatim"


def test_config_rejects_inverted_quote_limits() -> None:
    with pytest.raises(ValidationError):
        EvidencePackConfig(min_quote_tokens=100, max_quote_tokens=10)


def test_harness_token_counter_char_strategy_is_deterministic() -> None:
    from deerflow.utils.token_counting import count_text_tokens

    pack = EvidencePackAssembler(
        token_counter=lambda text: count_text_tokens(text, strategy="char")
    ).assemble(
        (_hit(1), _hit(2, document_id="doc-2")),
        release_id="release-1",
        config=EvidencePackConfig(token_budget=8000),
    )
    assert pack.status is EvidencePackStatus.READY
    assert pack.document_count == 2
