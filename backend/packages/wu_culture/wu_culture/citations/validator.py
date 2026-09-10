from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence

from wu_culture.evidence_pack import EvidencePack

from .contract import build_citation_contract, format_evidence_markdown_link
from .models import (
    AnswerCitation,
    CitationContract,
    CitationValidationResult,
    RejectedCitation,
)

# Matches [citation:LABEL](evidence://ID) including optional path/query after the id.
_EVIDENCE_CITATION_RE = re.compile(
    r"(?<!!)\[citation:\s*([^\]]+?)\]\(\s*evidence://([^)\s]+)\s*\)",
    re.IGNORECASE,
)
# Also catch bare evidence hrefs with non-citation markdown labels.
_GENERIC_EVIDENCE_LINK_RE = re.compile(
    r"(?<!!)\[([^\]]+?)\]\(\s*evidence://([^)\s]+)\s*\)",
    re.IGNORECASE,
)


def _normalize_evidence_id(raw: str) -> str:
    value = raw.strip()
    if "?" in value:
        value = value.split("?", 1)[0]
    if "#" in value:
        value = value.split("#", 1)[0]
    return value.strip("/")


def _parse_claimed_number(label: str) -> int | None:
    compact = label.strip()
    if compact.isdigit():
        return int(compact)
    match = re.fullmatch(r"[#\[]?(\d+)[\]\)]?", compact)
    if match:
        return int(match.group(1))
    return None


def _collect_contract(
    contract: CitationContract | None = None,
    *,
    pack: EvidencePack | None = None,
    citations: Sequence[AnswerCitation] | Mapping[str, AnswerCitation] | None = None,
    release_id: str = "unknown",
) -> CitationContract:
    if contract is not None:
        return contract
    if pack is not None:
        return build_citation_contract(pack)
    if citations is None:
        return CitationContract(release_id=release_id, citations=())
    if isinstance(citations, Mapping):
        ordered = tuple(
            citations[key]
            for key in sorted(citations, key=lambda item: citations[item].number)
        )
        return CitationContract(release_id=release_id, citations=ordered)
    return CitationContract(release_id=release_id, citations=tuple(citations))


def extract_evidence_ids_from_tool_payloads(payloads: Iterable[object]) -> list[str]:
    """Best-effort harvest of evidence IDs from search_sources tool JSON."""
    found: list[str] = []
    seen: set[str] = set()

    def add(evidence_id: str) -> None:
        if evidence_id and evidence_id not in seen:
            seen.add(evidence_id)
            found.append(evidence_id)

    def walk(node: object) -> None:
        if isinstance(node, dict):
            pack = node.get("evidence_pack")
            if isinstance(pack, dict):
                items = pack.get("items")
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and isinstance(item.get("evidence_id"), str):
                            add(item["evidence_id"])
            if isinstance(node.get("evidence_id"), str):
                add(node["evidence_id"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for payload in payloads:
        if isinstance(payload, str):
            text = payload.strip()
            if not text:
                continue
            try:
                walk(json.loads(text))
            except json.JSONDecodeError:
                for match in re.finditer(r"evidence://([^\s)\"']+)", text, flags=re.IGNORECASE):
                    add(_normalize_evidence_id(match.group(1)))
            continue
        walk(payload)
    return found


def validate_answer_citations(
    text: str,
    contract: CitationContract | None = None,
    *,
    pack: EvidencePack | None = None,
    citations: Sequence[AnswerCitation] | Mapping[str, AnswerCitation] | None = None,
    release_id: str = "unknown",
    drop_invalid: bool = True,
) -> CitationValidationResult:
    """Rewrite model text so every evidence citation maps to the pack contract.

    Invalid evidence IDs are dropped (or left marked) so the product never
    surfaces invented locators. Valid refs are renumbered to the stable pack
    number and retain book/volume/page metadata from the contract.
    """
    resolved = _collect_contract(
        contract,
        pack=pack,
        citations=citations,
        release_id=release_id,
    )
    by_id = resolved.by_evidence_id()
    valid: list[AnswerCitation] = []
    rejected: list[RejectedCitation] = []
    seen_ids: set[str] = set()
    rewritten = False

    def replace(match: re.Match[str]) -> str:
        nonlocal rewritten
        raw = match.group(0)
        label = match.group(1).strip()
        evidence_id = _normalize_evidence_id(match.group(2))
        claimed_number = _parse_claimed_number(label)

        citation = by_id.get(evidence_id)
        if citation is None and claimed_number is not None:
            # Number-only guesses are never enough without a known evidence id.
            rejected.append(
                RejectedCitation(
                    raw=raw,
                    reason="unknown_evidence_id",
                    claimed_evidence_id=evidence_id or None,
                    claimed_number=claimed_number,
                )
            )
            rewritten = True
            return "" if drop_invalid else raw

        if citation is None:
            rejected.append(
                RejectedCitation(
                    raw=raw,
                    reason="unknown_evidence_id",
                    claimed_evidence_id=evidence_id or None,
                    claimed_number=claimed_number,
                )
            )
            rewritten = True
            return "" if drop_invalid else raw

        if claimed_number is not None and claimed_number != citation.number:
            rewritten = True
        replacement = format_evidence_markdown_link(
            number=citation.number,
            evidence_id=citation.evidence_id,
        )
        if replacement != raw:
            rewritten = True
        if citation.evidence_id not in seen_ids:
            seen_ids.add(citation.evidence_id)
            valid.append(citation)
        return replacement

    # First pass: only explicit evidence:// citation protocol links.
    sanitized = _EVIDENCE_CITATION_RE.sub(replace, text)

    # Second pass: convert generic markdown links that already target evidence://
    # into the stable citation protocol (without double-processing).
    def replace_generic(match: re.Match[str]) -> str:
        nonlocal rewritten
        raw = match.group(0)
        if raw.lower().startswith("[citation:"):
            return raw
        label = match.group(1).strip()
        evidence_id = _normalize_evidence_id(match.group(2))
        citation = by_id.get(evidence_id)
        if citation is None:
            rejected.append(
                RejectedCitation(
                    raw=raw,
                    reason="unknown_evidence_id",
                    claimed_evidence_id=evidence_id or None,
                    claimed_number=_parse_claimed_number(label),
                )
            )
            rewritten = True
            return "" if drop_invalid else raw
        rewritten = True
        if citation.evidence_id not in seen_ids:
            seen_ids.add(citation.evidence_id)
            valid.append(citation)
        return format_evidence_markdown_link(
            number=citation.number,
            evidence_id=citation.evidence_id,
        )

    sanitized = _GENERIC_EVIDENCE_LINK_RE.sub(replace_generic, sanitized)

    # Collapse whitespace left by dropped citations without mangling paragraphs.
    cleaned = re.sub(r"[ \t]{2,}", " ", sanitized)
    cleaned = re.sub(r" ?\n{3,}", "\n\n", cleaned).strip()
    if cleaned != text.strip():
        rewritten = True

    # Preserve relative order of first appearance; numbers already stable.
    valid_sorted = tuple(sorted(valid, key=lambda item: item.number))
    return CitationValidationResult(
        original_text=text,
        sanitized_text=cleaned if drop_invalid else sanitized,
        valid_refs=valid_sorted,
        rejected=tuple(rejected),
        rewritten=rewritten,
    )


def contract_from_allowed_ids(
    evidence_ids: Sequence[str],
    *,
    locators: Mapping[str, Mapping[str, object]] | None = None,
    release_id: str = "unknown",
) -> CitationContract:
    """Build a minimal contract when only IDs (and optional locator maps) are known."""
    locators = locators or {}
    citations: list[AnswerCitation] = []
    for index, evidence_id in enumerate(evidence_ids, start=1):
        meta = locators.get(evidence_id, {})
        citations.append(
            AnswerCitation(
                number=index,
                evidence_id=evidence_id,
                chunk_id=str(meta.get("chunk_id") or f"chunk-{evidence_id}"),
                document_id=str(meta.get("document_id") or f"document-{evidence_id}"),
                document_title=str(meta.get("document_title") or evidence_id),
                edition=meta.get("edition") if isinstance(meta.get("edition"), str) else None,
                volume=meta.get("volume") if isinstance(meta.get("volume"), str) else None,
                section=meta.get("section") if isinstance(meta.get("section"), str) else None,
                page_start=int(meta.get("page_start") or 1),
                page_end=int(meta.get("page_end") or meta.get("page_start") or 1),
                quote=str(meta.get("quote") or "（证据原文已装入证据包）"),
                source_level=str(meta.get("source_level") or "A"),
                review_status=str(meta.get("review_status") or "reviewed"),
                href=f"evidence://{evidence_id}",
            )
        )
    return CitationContract(release_id=release_id, citations=tuple(citations))
