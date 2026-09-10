from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CleaningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class RawOcrPage(CleaningModel):
    source_file_id: str = Field(min_length=1)
    ocr_attempt_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    raw_text: str = Field(min_length=1)


class TextCleaningPolicy(CleaningModel):
    rule_version: str = Field(min_length=1)
    script_conversion: Literal["preserve", "simplified", "traditional"] = "preserve"
    variant_map: dict[str, str] = Field(default_factory=dict)
    normalize_line_endings: bool = True
    join_single_line_breaks: bool = True
    remove_repeated_headers: bool = True
    remove_repeated_footers: bool = True
    remove_page_number_footers: bool = True

    @field_validator("variant_map")
    @classmethod
    def validate_variant_map(cls, value: dict[str, str]) -> dict[str, str]:
        if any(len(before) != 1 or len(after) != 1 for before, after in value.items()):
            raise ValueError("variant_map entries must map one character to one character")
        return value


class TextChange(CleaningModel):
    sequence: int = Field(ge=0)
    rule_id: str = Field(min_length=1)
    raw_start: int = Field(ge=0)
    raw_end: int = Field(ge=0)
    clean_start: int = Field(ge=0)
    clean_end: int = Field(ge=0)
    before: str
    after: str


class CleanedPageContent(CleaningModel):
    source_file_id: str = Field(min_length=1)
    ocr_attempt_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    raw_text: str
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    clean_text: str
    clean_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rule_version: str = Field(min_length=1)
    script_conversion: Literal["preserve", "simplified", "traditional"]
    changes: tuple[TextChange, ...]

    @model_validator(mode="after")
    def validate_text_hashes(self) -> CleanedPageContent:
        if self.raw_sha256 != _text_sha256(self.raw_text):
            raise ValueError("raw_sha256 does not match raw_text")
        if self.clean_sha256 != _text_sha256(self.clean_text):
            raise ValueError("clean_sha256 does not match clean_text")
        return self


class CleanedOcrPage(CleanedPageContent):
    id: str = Field(min_length=1)
    generation_number: int = Field(ge=1)
    policy: TextCleaningPolicy
    generated_by: str = Field(min_length=1)
    generated_at: datetime

    @model_validator(mode="after")
    def validate_policy_snapshot(self) -> CleanedOcrPage:
        if self.rule_version != self.policy.rule_version or self.script_conversion != self.policy.script_conversion:
            raise ValueError("cleaning policy snapshot does not match result fields")
        return self


class TextCleaningRepository(Protocol):
    async def save(self, page: CleanedOcrPage) -> None: ...

    async def save_many(self, pages: Sequence[CleanedOcrPage]) -> None: ...

    async def list_generations(self, ocr_attempt_id: str) -> list[CleanedOcrPage]: ...

    async def list_latest(self, source_file_id: str) -> list[CleanedOcrPage]: ...

    async def list_page_generations(self, source_file_id: str, page_number: int) -> list[CleanedOcrPage]: ...


def clean_ocr_page(page: RawOcrPage, *, policy: TextCleaningPolicy) -> CleanedPageContent:
    return _clean_ocr_page(page, policy=policy, removals=())


def clean_ocr_pages(pages: Sequence[RawOcrPage], *, policy: TextCleaningPolicy) -> tuple[CleanedPageContent, ...]:
    page_lines = {page.ocr_attempt_id: _nonempty_line_spans(page.raw_text) for page in pages}
    header_counts = Counter(lines[0].text for lines in page_lines.values() if len(lines) >= 2)
    footer_counts = Counter(lines[-1].text for lines in page_lines.values() if len(lines) >= 2)
    repeated_headers = {text for text, count in header_counts.items() if count >= 2}
    repeated_footers = {text for text, count in footer_counts.items() if count >= 2}

    results = []
    for page in pages:
        lines = page_lines[page.ocr_attempt_id]
        removals: list[_RawRemoval] = []
        if policy.remove_repeated_headers and len(lines) >= 2 and lines[0].text in repeated_headers:
            removals.append(_removal_for_line(page.raw_text, lines[0], rule_id="remove_repeated_header", prefer_trailing_break=True))
        if len(lines) >= 2:
            footer = lines[-1]
            if policy.remove_page_number_footers and _PAGE_NUMBER.fullmatch(footer.text):
                removals.append(_removal_for_line(page.raw_text, footer, rule_id="remove_page_number_footer", prefer_trailing_break=False))
            elif policy.remove_repeated_footers and footer.text in repeated_footers and footer != lines[0]:
                removals.append(_removal_for_line(page.raw_text, footer, rule_id="remove_repeated_footer", prefer_trailing_break=False))
        results.append(_clean_ocr_page(page, policy=policy, removals=tuple(removals)))
    return tuple(results)


def _clean_ocr_page(page: RawOcrPage, *, policy: TextCleaningPolicy, removals: Sequence[_RawRemoval]) -> CleanedPageContent:
    units = [_TextUnit(value=character, raw_start=index, raw_end=index + 1) for index, character in enumerate(page.raw_text)]
    changes: list[TextChange] = []

    if policy.normalize_line_endings:
        index = 0
        while index < len(units):
            unit = units[index]
            if unit.value != "\r":
                index += 1
                continue
            has_lf = index + 1 < len(units) and units[index + 1].value == "\n"
            raw_end = units[index + 1].raw_end if has_lf else unit.raw_end
            before = "\r\n" if has_lf else "\r"
            clean_start = _clean_position(units, index)
            changes.append(
                TextChange(
                    sequence=len(changes),
                    rule_id="normalize_line_ending",
                    raw_start=unit.raw_start,
                    raw_end=raw_end,
                    clean_start=clean_start,
                    clean_end=clean_start + 1,
                    before=before,
                    after="\n",
                )
            )
            unit.value = "\n"
            unit.raw_end = raw_end
            if has_lf:
                units.pop(index + 1)
            index += 1

    for removal in removals:
        indexes = [index for index, unit in enumerate(units) if unit.raw_start >= removal.raw_start and unit.raw_end <= removal.raw_end]
        if not indexes:
            continue
        first_index = indexes[0]
        clean_start = _clean_position(units, first_index)
        before = "".join(units[index].value for index in indexes)
        changes.append(
            TextChange(
                sequence=len(changes),
                rule_id=removal.rule_id,
                raw_start=removal.raw_start,
                raw_end=removal.raw_end,
                clean_start=clean_start,
                clean_end=clean_start,
                before=before,
                after="",
            )
        )
        del units[first_index : indexes[-1] + 1]

    if policy.join_single_line_breaks:
        index = 0
        while index < len(units):
            unit = units[index]
            previous = units[index - 1].value if index > 0 else None
            following = units[index + 1].value if index + 1 < len(units) else None
            if unit.value != "\n" or previous == "\n" or following == "\n" or _is_structural_line_break(units, index):
                index += 1
                continue
            clean_start = _clean_position(units, index)
            changes.append(
                TextChange(
                    sequence=len(changes),
                    rule_id="join_single_line_break",
                    raw_start=unit.raw_start,
                    raw_end=unit.raw_end,
                    clean_start=clean_start,
                    clean_end=clean_start,
                    before=unit.value,
                    after="",
                )
            )
            units.pop(index)

    for index, unit in enumerate(units):
        converted = policy.variant_map.get(unit.value)
        if converted is None or converted == unit.value:
            continue
        clean_start = _clean_position(units, index)
        changes.append(
            TextChange(
                sequence=len(changes),
                rule_id="variant_map",
                raw_start=unit.raw_start,
                raw_end=unit.raw_end,
                clean_start=clean_start,
                clean_end=clean_start + len(converted),
                before=unit.value,
                after=converted,
            )
        )
        unit.value = converted

    if policy.script_conversion != "preserve":
        from opencc import OpenCC

        converter = OpenCC("t2s" if policy.script_conversion == "simplified" else "s2t")
        for index, unit in enumerate(units):
            converted = converter.convert(unit.value)
            if converted == unit.value:
                continue
            clean_start = _clean_position(units, index)
            changes.append(
                TextChange(
                    sequence=len(changes),
                    rule_id=f"script_{policy.script_conversion}",
                    raw_start=unit.raw_start,
                    raw_end=unit.raw_end,
                    clean_start=clean_start,
                    clean_end=clean_start + len(converted),
                    before=unit.value,
                    after=converted,
                )
            )
            unit.value = converted

    clean_text = "".join(unit.value for unit in units)

    return CleanedPageContent(
        source_file_id=page.source_file_id,
        ocr_attempt_id=page.ocr_attempt_id,
        page_number=page.page_number,
        raw_text=page.raw_text,
        raw_sha256=_text_sha256(page.raw_text),
        clean_text=clean_text,
        clean_sha256=_text_sha256(clean_text),
        rule_version=policy.rule_version,
        script_conversion=policy.script_conversion,
        changes=tuple(changes),
    )


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class _TextUnit:
    value: str
    raw_start: int
    raw_end: int


def _clean_position(units: list[_TextUnit], index: int) -> int:
    return sum(len(unit.value) for unit in units[:index])


@dataclass(frozen=True)
class _LineSpan:
    text: str
    raw_start: int
    raw_end: int


@dataclass(frozen=True)
class _RawRemoval:
    rule_id: str
    raw_start: int
    raw_end: int


_PAGE_NUMBER = re.compile(r"(?:[-—–]\s*\d+\s*[-—–]|(?:第\s*)?\d+\s*页)")
_STRUCTURAL_HEADING = re.compile(r"(?:(?:第)?[〇零一二三四五六七八九十百千0-9]+[卷章节目]|[卷目][〇零一二三四五六七八九十百千0-9]+)(?:\s+.*)?")


def _nonempty_line_spans(text: str) -> list[_LineSpan]:
    spans: list[_LineSpan] = []
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        line_without_break = raw_line.rstrip("\r\n")
        stripped = line_without_break.strip()
        if stripped:
            leading = len(line_without_break) - len(line_without_break.lstrip())
            spans.append(_LineSpan(text=stripped, raw_start=offset + leading, raw_end=offset + leading + len(stripped)))
        offset += len(raw_line)
    if not text.splitlines(keepends=True) and text.strip():
        leading = len(text) - len(text.lstrip())
        spans.append(_LineSpan(text=text.strip(), raw_start=leading, raw_end=leading + len(text.strip())))
    return spans


def _removal_for_line(text: str, line: _LineSpan, *, rule_id: str, prefer_trailing_break: bool) -> _RawRemoval:
    previous_lf = text.rfind("\n", 0, line.raw_start)
    physical_start = previous_lf + 1
    next_lf = text.find("\n", line.raw_end)
    physical_end = len(text) if next_lf < 0 else next_lf + 1
    start = physical_start
    end = physical_end
    if not prefer_trailing_break and start > 0:
        start -= 1
        if start > 0 and text[start - 1] == "\r":
            start -= 1
    return _RawRemoval(rule_id=rule_id, raw_start=start, raw_end=end)


def _is_structural_line_break(units: list[_TextUnit], index: int) -> bool:
    left = "".join(unit.value for unit in units[:index]).rsplit("\n", 1)[-1].strip()
    right = "".join(unit.value for unit in units[index + 1 :]).split("\n", 1)[0].strip()
    return bool(_STRUCTURAL_HEADING.fullmatch(left) or _STRUCTURAL_HEADING.fullmatch(right))
