from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from wu_culture.citations import build_citation_contract, format_evidence_markdown_link, validate_answer_citations
from wu_culture.conflicts import detect_conflicts
from wu_culture.evidence_pack import EvidencePackAssembler, EvidencePackConfig
from wu_culture.hybrid import HybridChannel, HybridSearchHit
from wu_culture.models import EvidenceRecord, SearchRequest, SearchStatus
from wu_culture.refusal import evaluate_refusal
from wu_culture.retrieval import EvidenceSearchService


class _LoopModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BridgeQALoopResult(_LoopModel):
    schema_version: Literal["bridge-qa-loop-v1"] = "bridge-qa-loop-v1"
    query: str
    status: str
    answer: str
    bridge_names: tuple[str, ...]
    citation_count: int = Field(ge=0)
    open_citations: tuple[dict[str, Any], ...]
    uncertainties: tuple[str, ...]
    conflict_report: dict[str, Any]
    refusal: dict[str, Any] | None
    evidence_pack: dict[str, Any]
    process_log: tuple[str, ...]


def _hits_from_search(service: EvidenceSearchService, request: SearchRequest) -> tuple[list[HybridSearchHit], SearchStatus, str]:
    response = service.search(request)
    hits: list[HybridSearchHit] = []
    for index, hit in enumerate(response.hits, start=1):
        hits.append(
            HybridSearchHit(
                release_id="synthetic-release",
                chunk_id=hit.chunk_id,
                fused_score=hit.score,
                channels=(HybridChannel.FULLTEXT,),
                fulltext_rank=index,
                fulltext_score=hit.score,
                citation=hit.citation,
            )
        )
    return hits, response.status, response.message


def _guess_bridges(quotes: list[str]) -> tuple[str, ...]:
    names: list[str] = []
    for quote in quotes:
        for token in ("甲桥", "乙桥", "丙桥", "普济桥", "如意桥"):
            if token in quote and token not in names:
                names.append(token)
    return tuple(names)


def run_bridge_qa_loop(
    service: EvidenceSearchService,
    *,
    query: str = "香溪沿岸有哪些古桥？",
    document_ids: list[str] | None = None,
    top_k: int = 5,
    pack_config: EvidencePackConfig | None = None,
) -> BridgeQALoopResult:
    """Deterministic vertical slice: retrieve → pack → cite/refuse → conflict."""
    log: list[str] = [f"query={query}"]
    request = SearchRequest(query=query, top_k=top_k)
    if document_ids:
        from wu_culture.models import SearchFilters

        request = SearchRequest(
            query=query,
            top_k=top_k,
            filters=SearchFilters(document_ids=document_ids),
        )
        log.append(f"document_scope={document_ids}")

    hits, status, message = _hits_from_search(service, request)
    log.append(f"search_status={status.value};hits={len(hits)};message={message}")

    def _assemble(current_hits, current_status):
        current_pack = EvidencePackAssembler(token_counter=len).assemble(
            current_hits,
            release_id="synthetic-release",
            config=pack_config or EvidencePackConfig(token_budget=8000),
        )
        current_refusal = evaluate_refusal(query=query, search_status=current_status, pack=current_pack)
        return current_pack, current_refusal

    pack, refusal = _assemble(hits, status)
    if refusal.decision.should_refuse:
        fallback_query = "香溪 桥"
        fallback_request = SearchRequest(query=fallback_query, top_k=top_k)
        if document_ids:
            from wu_culture.models import SearchFilters

            fallback_request = SearchRequest(
                query=fallback_query,
                top_k=top_k,
                filters=SearchFilters(document_ids=document_ids),
            )
        fb_hits, fb_status, fb_message = _hits_from_search(service, fallback_request)
        log.append(f"fallback_query={fallback_query};search_status={fb_status.value};hits={len(fb_hits)};message={fb_message}")
        fb_pack, fb_refusal = _assemble(fb_hits, fb_status)
        if (not fb_refusal.decision.should_refuse) or len(fb_pack.items) > len(pack.items):
            hits, status, pack, refusal = fb_hits, fb_status, fb_pack, fb_refusal

    log.append(f"evidence_pack_status={pack.status.value};items={len(pack.items)}")
    contract = build_citation_contract(pack)
    conflict = detect_conflicts(pack)
    log.append(f"refusal={refusal.decision.should_refuse};reason={refusal.decision.reason.value}")
    log.append(f"conflicts={conflict.has_conflicts};clusters={len(conflict.clusters)}")

    if refusal.decision.should_refuse:
        answer = refusal.text
        open_citations: tuple[dict[str, Any], ...] = ()
        bridges: tuple[str, ...] = ()
        uncertainties = (
            "当前检索范围内证据不足，桥梁清单无法确认。",
            "未检索到不等于历史上不存在。",
        )
        citation_count = 0
    else:
        bridges = _guess_bridges([item.quote for item in pack.items])
        # Build answer with at least two citations when available.
        cite_parts = []
        open_list: list[dict[str, Any]] = []
        for citation in contract.citations[: max(2, min(3, len(contract.citations)))]:
            cite_parts.append(format_evidence_markdown_link(number=citation.number, evidence_id=citation.evidence_id))
            open_list.append(
                {
                    "number": citation.number,
                    "evidence_id": citation.evidence_id,
                    "chunk_id": citation.chunk_id,
                    "document_title": citation.document_title,
                    "volume": citation.volume,
                    "page_start": citation.page_start,
                    "page_end": citation.page_end,
                    "href": citation.href,
                    "quote": citation.quote,
                }
            )
        bridge_text = "、".join(bridges) if bridges else "若干桥梁（见出处）"
        uncertainty_bits = []
        if any("未详" in item.quote or "待核" in item.quote or "传说" in item.quote for item in pack.items):
            uncertainty_bits.append("部分桥梁始建年代或位置仍待核验。")
        if conflict.has_conflicts:
            uncertainty_bits.append("多源记载存在差异，已并列保留，不自动裁定。")
        if not uncertainty_bits:
            uncertainty_bits.append("仍建议核对原书卷页。")

        answer = (
            f"根据当前已发布样例资料，香溪沿岸可见桥梁包括：{bridge_text}。"
            + "".join(cite_parts)
            + "\n"
            + "不确定项："
            + "；".join(uncertainty_bits)
        )
        validated = validate_answer_citations(answer, contract=contract)
        answer = validated.sanitized_text
        open_citations = tuple(open_list)
        citation_count = len(open_list)
        uncertainties = tuple(uncertainty_bits)
        log.append(f"citations={citation_count};rewritten={validated.rewritten}")

    return BridgeQALoopResult(
        query=query,
        status="refused" if refusal.decision.should_refuse else "answered",
        answer=answer,
        bridge_names=bridges,
        citation_count=citation_count,
        open_citations=open_citations,
        uncertainties=uncertainties,
        conflict_report=conflict.model_dump(mode="json"),
        refusal=refusal.model_dump(mode="json") if refusal.decision.should_refuse else None,
        evidence_pack=pack.model_dump(mode="json"),
        process_log=tuple(log),
    )


def load_synthetic_records(path: str) -> list[EvidenceRecord]:
    from pydantic import TypeAdapter

    payload = json.loads(open(path, encoding="utf-8").read())
    return TypeAdapter(list[EvidenceRecord]).validate_python(payload)
