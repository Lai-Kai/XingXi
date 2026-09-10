from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from .models import EvidencePack, EvidencePackConfig, EvidencePackItem, EvidencePackStatus

TokenCounter = Callable[[str], int]
ELLIPSIS = "\u2026"


class PackableHit(Protocol):
    """Minimal hit shape required by the assembler (HybridSearchHit satisfies this)."""

    chunk_id: str

    @property
    def citation(self) -> Any: ...


def _estimated_tokens(text: str) -> int:
    """Network-free CJK-aware fallback used outside the DeerFlow harness."""
    if not text:
        return 0
    cjk = sum(1 for char in text if unicodedata.east_asian_width(char) in {"W", "F"})
    return cjk + math.ceil((len(text) - cjk) / 4)


class EvidencePackAssembler:
    """Compress ranked retrieval hits into a budgeted, provenance-preserving pack.

    Design rules (stage 25):
    - Never invent or paraphrase source text; only prefix-truncate quotes.
    - Never truncate metadata (title/edition/volume/pages/level/review).
    - Prefer multi-document coverage when the budget is tight.
    - Preserve original retrieval rank order in the final pack.
    """

    def __init__(self, *, token_counter: TokenCounter | None = None) -> None:
        self._count_tokens = token_counter or _estimated_tokens

    def assemble(
        self,
        hits: Sequence[PackableHit],
        *,
        release_id: str,
        config: EvidencePackConfig | None = None,
    ) -> EvidencePack:
        config = config or EvidencePackConfig()
        unique, duplicate_count = self._deduplicate(hits)
        if not unique:
            return self._result(
                release_id=release_id,
                config=config,
                status=EvidencePackStatus.EMPTY,
                input_count=len(hits),
                deduplicated_count=duplicate_count,
                items=(),
            )

        # Coverage first (one representative per document), then remaining by rank.
        candidates = self._coverage_order(unique)[: config.max_items]
        selected: list[EvidencePackItem] = []
        used_tokens = 0
        minimum_costs = [self._minimum_item_tokens(rank, hit, config) for rank, hit in candidates]

        for index, (rank, hit) in enumerate(candidates):
            remaining = config.token_budget - used_tokens
            if remaining <= 0:
                break
            # Reserve room for later documents so multi-source is not starved by
            # an oversized first quote (LangChain-style budget compression idea).
            current_minimum = minimum_costs[index]
            reserve = 0
            for future_cost in minimum_costs[index + 1 :]:
                if current_minimum + reserve + future_cost > remaining:
                    break
                reserve += future_cost
            item = self._fit_item(rank, hit, remaining - reserve, config)
            if item is None:
                continue
            cost = self._item_tokens(item)
            if cost > remaining:
                continue
            selected.append(item)
            used_tokens += cost

        selected.sort(key=lambda item: item.rank)
        status = EvidencePackStatus.READY if selected else EvidencePackStatus.INSUFFICIENT_BUDGET
        return self._result(
            release_id=release_id,
            config=config,
            status=status,
            input_count=len(hits),
            deduplicated_count=duplicate_count,
            items=tuple(selected),
            used_tokens=used_tokens,
        )

    @staticmethod
    def _deduplicate(hits: Sequence[PackableHit]) -> tuple[list[tuple[int, PackableHit]], int]:
        seen_evidence: set[str] = set()
        seen_chunks: set[str] = set()
        seen_document_quotes: set[tuple[str, str]] = set()
        unique: list[tuple[int, PackableHit]] = []
        for rank, hit in enumerate(hits, start=1):
            evidence_id = str(hit.citation.evidence_id)
            chunk_id = str(hit.chunk_id)
            document_quote = (
                str(hit.citation.document_id),
                " ".join(str(hit.citation.quote).split()),
            )
            if evidence_id in seen_evidence or chunk_id in seen_chunks or document_quote in seen_document_quotes:
                continue
            seen_evidence.add(evidence_id)
            seen_chunks.add(chunk_id)
            seen_document_quotes.add(document_quote)
            unique.append((rank, hit))
        return unique, len(hits) - len(unique)

    @staticmethod
    def _coverage_order(unique: list[tuple[int, PackableHit]]) -> list[tuple[int, PackableHit]]:
        representatives: list[tuple[int, PackableHit]] = []
        repeated: list[tuple[int, PackableHit]] = []
        seen_documents: set[str] = set()
        for candidate in unique:
            document_id = str(candidate[1].citation.document_id)
            if document_id in seen_documents:
                repeated.append(candidate)
            else:
                seen_documents.add(document_id)
                representatives.append(candidate)
        return representatives + repeated

    def _fit_item(
        self,
        rank: int,
        hit: PackableHit,
        token_budget: int,
        config: EvidencePackConfig,
    ) -> EvidencePackItem | None:
        if token_budget <= 0:
            return None
        quote = str(hit.citation.quote)
        capped_quote = self._truncate_to_tokens(quote, config.max_quote_tokens)
        item = self._make_item(rank, hit, capped_quote)
        if self._item_tokens(item) <= token_budget:
            return item

        minimum = self._truncate_to_tokens(quote, config.min_quote_tokens)
        minimum_item = self._make_item(rank, hit, minimum)
        if self._item_tokens(minimum_item) > token_budget:
            return None

        # Binary search longest prefix that still fits the remaining budget.
        low = len(minimum.removesuffix(ELLIPSIS))
        high = len(capped_quote.removesuffix(ELLIPSIS))
        best = minimum_item
        while low <= high:
            middle = (low + high) // 2
            candidate_quote = self._prefix_quote(quote, middle)
            candidate = self._make_item(rank, hit, candidate_quote)
            if self._item_tokens(candidate) <= token_budget:
                best = candidate
                low = middle + 1
            else:
                high = middle - 1
        return best

    def _minimum_item_tokens(self, rank: int, hit: PackableHit, config: EvidencePackConfig) -> int:
        quote = self._truncate_to_tokens(str(hit.citation.quote), config.min_quote_tokens)
        return self._item_tokens(self._make_item(rank, hit, quote))

    def _truncate_to_tokens(self, quote: str, token_limit: int) -> str:
        if self._count_tokens(quote) <= token_limit:
            return quote
        low, high, best = 1, len(quote), self._prefix_quote(quote, 1)
        while low <= high:
            middle = (low + high) // 2
            candidate = self._prefix_quote(quote, middle)
            if self._count_tokens(candidate) <= token_limit:
                best = candidate
                low = middle + 1
            else:
                high = middle - 1
        return best

    @staticmethod
    def _prefix_quote(original: str, length: int) -> str:
        if length >= len(original):
            return original
        return original[: max(1, length)].rstrip() + ELLIPSIS

    @staticmethod
    def _make_item(rank: int, hit: PackableHit, quote: str) -> EvidencePackItem:
        citation = hit.citation
        original = str(citation.quote)
        truncated = quote != original
        # Safety: packed quote must always be a verbatim prefix of the original.
        if truncated:
            body = quote.removesuffix(ELLIPSIS)
            if not original.startswith(body):
                raise ValueError("refusing to emit non-verbatim packed quote")
        elif quote != original:
            raise ValueError("verbatim quote mismatch")
        return EvidencePackItem(
            rank=rank,
            evidence_id=str(citation.evidence_id),
            chunk_id=str(hit.chunk_id),
            document_id=str(citation.document_id),
            source_file_id=getattr(citation, "source_file_id", None),
            document_title=str(citation.document_title),
            edition=citation.edition,
            volume=citation.volume,
            section=citation.section,
            page_start=int(citation.page_start),
            page_end=int(citation.page_end),
            folio_start=getattr(citation, "folio_start", None),
            folio_end=getattr(citation, "folio_end", None),
            quote=quote,
            quote_provenance="truncated_verbatim" if truncated else "verbatim",
            quote_truncated=truncated,
            original_quote_chars=len(original),
            original_quote_sha256=hashlib.sha256(original.encode("utf-8")).hexdigest(),
            source_level=citation.source_level,
            review_status=citation.review_status,
        )

    def _item_tokens(self, item: EvidencePackItem) -> int:
        payload = json.dumps(
            item.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return self._count_tokens(payload)

    @staticmethod
    def _result(
        *,
        release_id: str,
        config: EvidencePackConfig,
        status: EvidencePackStatus,
        input_count: int,
        deduplicated_count: int,
        items: tuple[EvidencePackItem, ...],
        used_tokens: int = 0,
    ) -> EvidencePack:
        return EvidencePack(
            release_id=release_id,
            status=status,
            token_budget=config.token_budget,
            used_tokens=used_tokens,
            input_count=input_count,
            deduplicated_count=deduplicated_count,
            omitted_count=max(0, input_count - deduplicated_count - len(items)),
            document_count=len({item.document_id for item in items}),
            items=items,
        )
