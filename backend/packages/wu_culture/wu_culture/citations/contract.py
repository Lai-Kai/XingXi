from __future__ import annotations

from wu_culture.evidence_pack import EvidencePack, EvidencePackItem

from .models import AnswerCitation, CitationContract, EvidenceDetail

EVIDENCE_SCHEME = "evidence://"


def format_evidence_href(evidence_id: str) -> str:
    return f"{EVIDENCE_SCHEME}{evidence_id}"


def format_evidence_markdown_link(*, number: int, evidence_id: str, label: str | None = None) -> str:
    text = label if label is not None else str(number)
    return f"[citation:{text}]({format_evidence_href(evidence_id)})"


def _item_to_citation(item: EvidencePackItem, number: int) -> AnswerCitation:
    return AnswerCitation(
        number=number,
        evidence_id=item.evidence_id,
        chunk_id=item.chunk_id,
        document_id=item.document_id,
        source_file_id=item.source_file_id,
        document_title=item.document_title,
        edition=item.edition,
        volume=item.volume,
        section=item.section,
        page_start=item.page_start,
        page_end=item.page_end,
        folio_start=item.folio_start,
        folio_end=item.folio_end,
        quote=item.quote,
        source_level=item.source_level.value if hasattr(item.source_level, "value") else str(item.source_level),
        review_status=item.review_status.value if hasattr(item.review_status, "value") else str(item.review_status),
        href=format_evidence_href(item.evidence_id),
    )


def build_citation_contract(pack: EvidencePack) -> CitationContract:
    """Map evidence-pack order to stable 1-based citation numbers."""
    ordered = sorted(pack.items, key=lambda item: item.rank)
    citations = tuple(_item_to_citation(item, index) for index, item in enumerate(ordered, start=1))
    return CitationContract(release_id=pack.release_id, citations=citations)


def evidence_detail_from_pack_item(item: EvidencePackItem) -> EvidenceDetail:
    return EvidenceDetail(
        evidence_id=item.evidence_id,
        chunk_id=item.chunk_id,
        document_id=item.document_id,
        source_file_id=item.source_file_id,
        document_title=item.document_title,
        edition=item.edition,
        volume=item.volume,
        section=item.section,
        page_start=item.page_start,
        page_end=item.page_end,
        folio_start=item.folio_start,
        folio_end=item.folio_end,
        quote=item.quote,
        source_level=item.source_level.value if hasattr(item.source_level, "value") else str(item.source_level),
        review_status=item.review_status.value if hasattr(item.review_status, "value") else str(item.review_status),
        href=format_evidence_href(item.evidence_id),
    )


def evidence_detail_from_record(record) -> EvidenceDetail:
    """Map a domain EvidenceRecord to the clickable detail contract."""
    evidence = record.evidence
    document = record.document
    chunk = record.chunk
    return EvidenceDetail(
        evidence_id=evidence.id,
        chunk_id=evidence.chunk_id,
        document_id=evidence.document_id,
        document_title=document.title,
        edition=document.edition,
        volume=chunk.volume,
        section=chunk.section,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        quote=evidence.quote,
        source_level=evidence.source_level.value if hasattr(evidence.source_level, "value") else str(evidence.source_level),
        review_status=evidence.review_status.value if hasattr(evidence.review_status, "value") else str(evidence.review_status),
        href=format_evidence_href(evidence.id),
    )
