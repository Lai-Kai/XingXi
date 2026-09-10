from __future__ import annotations

import re
from collections.abc import Sequence

from wu_culture.evidence_pack import EvidencePack, EvidencePackItem, EvidencePackStatus
from wu_culture.models import SearchStatus, SourceLevel

from .models import RefusalDecision, RefusalReason, RefusalResponse

REFUSAL_CANONICAL_MESSAGE = "当前检索范围内暂无明确记载"

_NONEXISTENCE_PATTERNS = (
    re.compile(r"历史上不存在"),
    re.compile(r"从未存在"),
    re.compile(r"可以断定不存在"),
    re.compile(r"确定没有"),
    re.compile(r"并无此[人物地]"),
    re.compile(r"there (?:is|was) no\b", re.IGNORECASE),
    re.compile(r"never existed", re.IGNORECASE),
)

_LOW_GRADES = {SourceLevel.D, SourceLevel.E, SourceLevel.U, "D", "E", "U", "d", "e", "u"}


def is_historical_nonexistence_claim(text: str) -> bool:
    return any(pattern.search(text) for pattern in _NONEXISTENCE_PATTERNS)


def _item_level(item: EvidencePackItem) -> str:
    level = item.source_level
    return level.value if hasattr(level, "value") else str(level)


def _usable_items(items: Sequence[EvidencePackItem]) -> list[EvidencePackItem]:
    usable: list[EvidencePackItem] = []
    for item in items:
        level = _item_level(item)
        if level in _LOW_GRADES:
            continue
        usable.append(item)
    return usable


def _query_terms(query: str) -> set[str]:
    normalized = re.sub(r"[^0-9a-zA-Z\u3400-\u9fff]+", "", query.casefold())
    if len(normalized) <= 2:
        return {normalized} if normalized else set()
    return {normalized[i : i + 2] for i in range(len(normalized) - 1)}


def _items_match_query(items: Sequence[EvidencePackItem], query: str) -> bool:
    terms = _query_terms(query)
    if not terms:
        return bool(items)
    for item in items:
        haystack = re.sub(
            r"[^0-9a-zA-Z\u3400-\u9fff]+",
            "",
            f"{item.document_title}{item.volume or ''}{item.section or ''}{item.quote}".casefold(),
        )
        matched = sum(1 for term in terms if term and term in haystack)
        if matched >= (1 if len(terms) <= 2 else 2):
            return True
    return False


def evaluate_refusal(
    *,
    query: str,
    search_status: str | SearchStatus | None = None,
    pack: EvidencePack | None = None,
    release_id: str | None = None,
    document_ids: Sequence[str] | None = None,
    min_usable_evidence: int = 1,
    allow_inferred_answer: bool = False,
) -> RefusalResponse:
    """Decide whether the agent must refuse a factual historical answer."""
    status = (
        search_status.value
        if isinstance(search_status, SearchStatus)
        else (search_status or (pack.status.value if pack is not None else SearchStatus.INSUFFICIENT.value))
    )
    items = tuple(pack.items) if pack is not None else ()
    usable = _usable_items(items)
    document_scope = tuple(document_ids or sorted({item.document_id for item in items}))
    notes: list[str] = []

    reason = RefusalReason.NONE
    should_refuse = False

    if pack is not None and pack.status is EvidencePackStatus.EMPTY:
        should_refuse = True
        reason = RefusalReason.EMPTY_RESULTS
        notes.append("证据包状态为空")
    elif pack is not None and pack.status is EvidencePackStatus.INSUFFICIENT_BUDGET and not items:
        should_refuse = True
        reason = RefusalReason.BUDGET_EXHAUSTED
        notes.append("token 预算不足，无法装入任何证据")
    elif status in {SearchStatus.INSUFFICIENT.value, "insufficient"} and not items:
        should_refuse = True
        reason = RefusalReason.EMPTY_RESULTS
        notes.append("检索返回 insufficient 且无证据")
    elif not items:
        should_refuse = True
        reason = RefusalReason.INSUFFICIENT_PACK
        notes.append("缺少可验证的证据包")
    elif items and not usable:
        reason = RefusalReason.LOW_GRADE_ONLY
        if allow_inferred_answer:
            notes.append("仅有 D/E 级材料，允许推断性回答")
        else:
            should_refuse = True
            reason = RefusalReason.LOW_GRADE_ONLY
            notes.append("仅有 D/E 级材料，不得写成确定史实")
    elif items and not _items_match_query(items, query):
        should_refuse = True
        reason = RefusalReason.EVIDENCE_MISMATCH
        notes.append("证据文本与问题关键词不匹配")
    elif len(usable) < min_usable_evidence and status != SearchStatus.SUPPORTED.value:
        should_refuse = True
        reason = RefusalReason.INSUFFICIENT_PACK
        notes.append(f"可用证据数 {len(usable)} 低于阈值 {min_usable_evidence}")

    decision = RefusalDecision(
        should_refuse=should_refuse,
        reason=reason,
        search_status=status,
        query=query,
        release_id=release_id or (pack.release_id if pack is not None else None),
        document_scope=document_scope,
        evidence_count=len(items),
        usable_evidence_count=len(usable),
        allowed_source_levels=tuple(sorted({_item_level(item) for item in usable})),
        notes=tuple(notes),
    )
    return build_refusal_response(decision)


def build_refusal_response(decision: RefusalDecision) -> RefusalResponse:
    scope_parts = []
    if decision.release_id:
        scope_parts.append(f"知识版本 {decision.release_id}")
    if decision.document_scope:
        scope_parts.append(f"限定文献 {len(decision.document_scope)} 种")
    else:
        scope_parts.append("当前已发布检索索引")
    scope_parts.append(f"可用证据 {decision.usable_evidence_count} 条")
    search_scope_summary = "；".join(scope_parts)

    next_steps: list[str] = []
    if decision.reason is RefusalReason.LOW_GRADE_ONLY:
        next_steps.append("补充或复核 A/B/C 级方志、碑刻或档案材料后再问")
    if decision.reason is RefusalReason.EVIDENCE_MISMATCH:
        next_steps.append("改用更具体的地名/人物/卷目关键词，或扩大文献范围")
    if decision.reason is RefusalReason.EMPTY_RESULTS:
        next_steps.append("检查是否限定了错误知识版本或文献集合")
        next_steps.append("可改写提问，或提供可授权的新史料入库")
    if decision.reason is RefusalReason.BUDGET_EXHAUSTED:
        next_steps.append("提高证据包 token 预算后重试")
    if not next_steps:
        next_steps.append("可继续检索相关人物、地点或卷目")

    if decision.should_refuse:
        message = REFUSAL_CANONICAL_MESSAGE
        text = render_refusal_text(decision, search_scope_summary, tuple(next_steps))
    elif decision.reason is RefusalReason.LOW_GRADE_ONLY:
        message = "已检索到低等级材料，仅供补充分析"
        text = ""
    else:
        message = "已检索到可引用证据"
        text = ""

    return RefusalResponse(
        decision=decision,
        message=message,
        search_scope_summary=search_scope_summary,
        next_steps=tuple(next_steps),
        text=text,
    )


def render_refusal_text(
    decision: RefusalDecision,
    search_scope_summary: str,
    next_steps: Sequence[str],
) -> str:
    lines = [
        REFUSAL_CANONICAL_MESSAGE + "。",
        f"检索范围：{search_scope_summary}。",
        "说明：这只表示当前检索范围内未找到足够可引用记载，并不等于历史上不存在。",
    ]
    if decision.notes:
        lines.append("原因：" + "；".join(decision.notes) + "。")
    if next_steps:
        lines.append("可继续查找：" + "；".join(next_steps) + "。")
    return "\n".join(lines)
