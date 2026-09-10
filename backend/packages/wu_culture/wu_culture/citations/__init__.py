"""Answer citation contract: stable evidence-backed markdown references."""

from __future__ import annotations

from .contract import build_citation_contract, format_evidence_href, format_evidence_markdown_link
from .models import (
    AnswerCitation,
    CitationContract,
    CitationValidationResult,
    EvidenceDetail,
    RejectedCitation,
)
from .validator import validate_answer_citations

__all__ = [
    "AnswerCitation",
    "CitationContract",
    "CitationValidationResult",
    "EvidenceDetail",
    "RejectedCitation",
    "build_citation_contract",
    "format_evidence_href",
    "format_evidence_markdown_link",
    "validate_answer_citations",
]
