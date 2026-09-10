from __future__ import annotations

from wu_culture.conflicts import ConflictType, detect_conflicts
from wu_culture.evidence_pack import EvidencePack, EvidencePackItem, EvidencePackStatus
from wu_culture.models import ReviewStatus, SourceLevel


def _item(
    *,
    evidence_id: str,
    title: str,
    quote: str,
    level: SourceLevel = SourceLevel.A,
    edition: str | None = "清刻本",
    page: int = 10,
) -> EvidencePackItem:
    return EvidencePackItem(
        rank=int(evidence_id.rsplit("-", 1)[-1]) if evidence_id[-1].isdigit() else 1,
        evidence_id=evidence_id,
        chunk_id=f"chunk-{evidence_id}",
        document_id=f"doc-{evidence_id}",
        document_title=title,
        edition=edition,
        volume="卷一",
        section="桥梁",
        page_start=page,
        page_end=page,
        quote=quote,
        quote_provenance="verbatim",
        quote_truncated=False,
        original_quote_chars=len(quote),
        original_quote_sha256="b" * 64,
        source_level=level,
        review_status=ReviewStatus.REVIEWED,
    )


def test_year_conflict_is_marked_without_dropping_low_grade() -> None:
    pack = EvidencePack(
        release_id="release-1",
        status=EvidencePackStatus.READY,
        token_budget=4000,
        used_tokens=200,
        input_count=2,
        deduplicated_count=0,
        omitted_count=0,
        document_count=2,
        items=(
            _item(evidence_id="e-1", title="《木渎小志》", quote="普济桥建于乾隆十二年。", level=SourceLevel.A),
            _item(evidence_id="e-2", title="《木渎镇志》", quote="普济桥建于道光三年。", level=SourceLevel.D),
        ),
    )
    report = detect_conflicts(pack)

    assert report.has_conflicts is True
    assert any(cluster.conflict_type is ConflictType.YEAR for cluster in report.clusters)
    year_cluster = next(cluster for cluster in report.clusters if cluster.conflict_type is ConflictType.YEAR)
    assert {v.evidence_id for v in year_cluster.variants} == {"e-1", "e-2"}
    assert report.retained_low_grade is True
    assert any("不替专家裁定" in note for note in report.notes)


def test_person_name_conflict() -> None:
    pack = EvidencePack(
        release_id="release-1",
        status=EvidencePackStatus.READY,
        token_budget=4000,
        used_tokens=200,
        input_count=2,
        deduplicated_count=0,
        omitted_count=0,
        document_count=2,
        items=(
            _item(evidence_id="e-1", title="《木渎小志》", quote="顾氏先生曾修普济桥。"),
            _item(evidence_id="e-2", title="《木渎镇志》", quote="沈氏先生曾修普济桥。"),
        ),
    )
    report = detect_conflicts(pack)
    assert any(cluster.conflict_type is ConflictType.PERSON for cluster in report.clusters)


def test_edition_text_diff_uses_diff_match_patch() -> None:
    pack = EvidencePack(
        release_id="release-1",
        status=EvidencePackStatus.READY,
        token_budget=4000,
        used_tokens=200,
        input_count=2,
        deduplicated_count=0,
        omitted_count=0,
        document_count=2,
        items=(
            _item(evidence_id="e-1", title="《木渎小志》", quote="香溪之滨有普济桥，石梁三孔。", edition="民国铅印本"),
            _item(evidence_id="e-2", title="《木渎小志》", quote="香溪之滨有普济桥，石梁五孔。", edition="清抄本"),
        ),
    )
    report = detect_conflicts(pack)
    text_clusters = [c for c in report.clusters if c.conflict_type is ConflictType.TEXT]
    assert text_clusters
    assert text_clusters[0].diff_snippets
    assert any("三孔" in snip or "五孔" in snip or snip.startswith(("+", "-")) for snip in text_clusters[0].diff_snippets)


def test_no_conflict_for_identical_claims() -> None:
    quote = "香溪沿岸有普济桥。"
    pack = EvidencePack(
        release_id="release-1",
        status=EvidencePackStatus.READY,
        token_budget=4000,
        used_tokens=100,
        input_count=2,
        deduplicated_count=0,
        omitted_count=0,
        document_count=2,
        items=(
            _item(evidence_id="e-1", title="《木渎小志》", quote=quote),
            _item(evidence_id="e-2", title="《木渎镇志》", quote=quote),
        ),
    )
    report = detect_conflicts(pack)
    assert report.has_conflicts is False


def test_same_document_fragments_are_not_cross_source_conflicts() -> None:
    pack = EvidencePack(
        release_id="release-1",
        status=EvidencePackStatus.READY,
        token_budget=4000,
        used_tokens=200,
        input_count=2,
        deduplicated_count=0,
        omitted_count=0,
        document_count=1,
        items=(
            _item(evidence_id="e-1", title="《木渎小志》", quote="顾氏先生修桥，始于乾隆十二年。").model_copy(update={"document_id": "doc-shared"}),
            _item(evidence_id="e-2", title="《木渎小志》", quote="沈氏先生修桥，道光三年重修。").model_copy(update={"document_id": "doc-shared"}),
        ),
    )

    report = detect_conflicts(pack)

    assert report.has_conflicts is False
