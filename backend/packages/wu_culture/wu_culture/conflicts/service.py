from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence

from diff_match_patch import diff_match_patch

from wu_culture.evidence_pack import EvidencePack, EvidencePackItem

from .models import (
    ClaimVariant,
    ConflictCluster,
    ConflictReport,
    ConflictType,
    UncertaintyLevel,
)

_YEAR_RE = re.compile(
    r"(?:公元前\s*\d{1,4}\s*年|\d{3,4}\s*年|[唐宋元明清](?:初|中|末|季)?|"
    r"康熙|雍正|乾隆|嘉庆|道光|咸丰|同治|光绪|宣统|"
    r"顺治|洪武|永乐|嘉靖|万历|崇祯)"
)
_PERSON_HINTS = ("氏", "公", "先生", "太守", "知县", "员外", "状元")
_PLACE_HINTS = ("桥", "寺", "巷", "街", "村", "镇", "山", "河", "溪", "园", "塘", "浜")


def _level(item: EvidencePackItem) -> str:
    value = item.source_level
    return value.value if hasattr(value, "value") else str(value)


def _review(item: EvidencePackItem) -> str:
    value = item.review_status
    return value.value if hasattr(value, "value") else str(value)


def _years(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match.group(0).replace(" ", "") for match in _YEAR_RE.finditer(text)))


def _hint_mentions(text: str, hints: Sequence[str]) -> tuple[str, ...]:
    found: list[str] = []
    for match in re.finditer(r"[\u4e00-\u9fff]{2,8}", text):
        token = match.group(0)
        if any(hint in token for hint in hints):
            found.append(token)
    return tuple(dict.fromkeys(found))


def _to_variant(item: EvidencePackItem) -> ClaimVariant:
    text = item.quote
    return ClaimVariant(
        evidence_id=item.evidence_id,
        document_title=item.document_title,
        edition=item.edition,
        volume=item.volume,
        page_start=item.page_start,
        page_end=item.page_end,
        source_level=_level(item),
        review_status=_review(item),
        claim_text=text,
        year_mentions=_years(text),
        person_mentions=_hint_mentions(text, _PERSON_HINTS),
        place_mentions=_hint_mentions(text, _PLACE_HINTS),
    )


def _text_diff_snippets(left: str, right: str, *, limit: int = 3) -> tuple[str, ...]:
    dmp = diff_match_patch()
    diffs = dmp.diff_main(left, right)
    dmp.diff_cleanupSemantic(diffs)
    snippets: list[str] = []
    for op, data in diffs:
        if not data or data.isspace():
            continue
        if op == dmp.DIFF_INSERT:
            snippets.append(f"+{data[:40]}")
        elif op == dmp.DIFF_DELETE:
            snippets.append(f"-{data[:40]}")
        if len(snippets) >= limit:
            break
    return tuple(snippets)


def _uncertainty_for(count: int, types: set[ConflictType]) -> UncertaintyLevel:
    if not types:
        return UncertaintyLevel.NONE
    if ConflictType.YEAR in types or ConflictType.PERSON in types:
        return UncertaintyLevel.HIGH if count >= 2 else UncertaintyLevel.MEDIUM
    if ConflictType.PLACE in types:
        return UncertaintyLevel.MEDIUM
    return UncertaintyLevel.LOW


def detect_conflicts(pack: EvidencePack) -> ConflictReport:
    """Detect multi-source disagreements without dropping low-grade claims."""
    variants = [_to_variant(item) for item in pack.items]
    clusters: list[ConflictCluster] = []
    retained_low_grade = any(v.source_level in {"D", "E"} for v in variants)

    # Year conflicts: different year mentions across items.
    year_map: dict[str, list[ClaimVariant]] = defaultdict(list)
    for variant in variants:
        for year in variant.year_mentions or ("（未载年代）",):
            year_map[year].append(variant)
    year_keys = [key for key, group in year_map.items() if key != "（未载年代）"]
    year_sources = {
        (variant.document_title, variant.edition)
        for key in year_keys
        for variant in year_map[key]
    }
    if len(year_keys) >= 2 and len(year_sources) >= 2:
        involved = []
        seen = set()
        for key in year_keys:
            for variant in year_map[key]:
                if variant.evidence_id not in seen:
                    seen.add(variant.evidence_id)
                    involved.append(variant)
        summary = "；".join(f"{key}（{len(year_map[key])}条）" for key in year_keys)
        clusters.append(
            ConflictCluster(
                conflict_type=ConflictType.YEAR,
                topic="年代记载",
                summary=f"多源对年代记载不一致：{summary}",
                uncertainty=UncertaintyLevel.HIGH,
                variants=tuple(involved),
                diff_snippets=tuple(year_keys),
            )
        )

    # Person / place: shared prefix token groups with divergent continuations are hard;
    # mark conflict when two items mention different non-overlapping person/place sets
    # while both non-empty and documents differ.
    for conflict_type, attr, topic in (
        (ConflictType.PERSON, "person_mentions", "人物记载"),
        (ConflictType.PLACE, "place_mentions", "地点记载"),
    ):
        nonempty = [v for v in variants if getattr(v, attr)]
        if len(nonempty) < 2:
            continue
        sets = [set(getattr(v, attr)) for v in nonempty]
        union = set.union(*sets) if sets else set()
        inter = set.intersection(*sets) if sets else set()
        if union and inter != union and len(union - inter) >= 1:
            # Only flag when documents disagree, not when one is superset lightly.
            if any(s - inter for s in sets) and len({(v.document_title, v.edition) for v in nonempty}) >= 2:
                labels = sorted(union - inter)
                clusters.append(
                    ConflictCluster(
                        conflict_type=conflict_type,
                        topic=topic,
                        summary=f"多源对{topic[:-2]}称谓/对象不一致：{'、'.join(labels[:6])}",
                        uncertainty=UncertaintyLevel.MEDIUM if conflict_type is ConflictType.PLACE else UncertaintyLevel.HIGH,
                        variants=tuple(nonempty),
                        diff_snippets=tuple(labels[:6]),
                    )
                )

    # Edition / text diffs across pairs from different documents.
    for index, left in enumerate(variants):
        for right in variants[index + 1 :]:
            if left.claim_text == right.claim_text:
                continue
            if left.document_title == right.document_title and left.edition == right.edition:
                # Same-edition near-duplicates are not cross-source conflicts.
                continue
            snippets = _text_diff_snippets(left.claim_text, right.claim_text)
            # Only emit text conflict when quotes are similar enough to be comparable
            # or when no structured conflict already covers the pair.
            ratio_proxy = abs(len(left.claim_text) - len(right.claim_text))
            shared = set(left.claim_text) & set(right.claim_text)
            if snippets and (ratio_proxy < max(len(left.claim_text), len(right.claim_text)) or len(shared) >= 4):
                clusters.append(
                    ConflictCluster(
                        conflict_type=ConflictType.TEXT,
                        topic="原文表述",
                        summary=(
                            f"《{left.document_title}》与《{right.document_title}》"
                            f"对同一主题表述存在差异"
                        ),
                        uncertainty=UncertaintyLevel.LOW,
                        variants=(left, right),
                        diff_snippets=snippets,
                    )
                )

    # Deduplicate text clusters that only restate year/person already found: keep all;
    # product prefers explicit presentation.
    types = {cluster.conflict_type for cluster in clusters}
    uncertainty = _uncertainty_for(len(clusters), types)
    notes = []
    if retained_low_grade:
        notes.append("低等级来源未因冲突被删除，仅并列展示")
    if clusters:
        notes.append("系统不替专家裁定尚无定论的历史争议")

    return ConflictReport(
        release_id=pack.release_id,
        has_conflicts=bool(clusters),
        uncertainty=uncertainty,
        clusters=tuple(clusters),
        retained_low_grade=retained_low_grade,
        notes=tuple(notes),
    )
