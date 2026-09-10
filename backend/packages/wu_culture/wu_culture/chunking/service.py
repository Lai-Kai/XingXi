from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChunkingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class ChunkSourcePage(ChunkingModel):
    cleaned_page_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    raw_text: str = Field(min_length=1)
    clean_text: str = Field(min_length=1)


class ChunkingPolicy(ChunkingModel):
    split_version: str = Field(min_length=1)
    max_characters: int = Field(default=1000, ge=50, le=20000)
    overlap_characters: int = Field(default=100, ge=0, le=5000)

    @model_validator(mode="after")
    def validate_window(self) -> ChunkingPolicy:
        if self.overlap_characters >= self.max_characters:
            raise ValueError("overlap_characters must be smaller than max_characters")
        return self


class StructureNode(ChunkingModel):
    id: str = Field(min_length=1)
    kind: Literal["volume", "item"]
    title: str = Field(min_length=1)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    children: tuple[StructureNode, ...] = ()


class StructuredChunk(ChunkingModel):
    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    source_file_id: str = Field(min_length=1)
    split_version: str = Field(min_length=1)
    chunk_index: int = Field(ge=0)
    volume: str | None = None
    item: str | None = None
    paragraph_index: int = Field(ge=0)
    paragraph_char_start: int = Field(ge=0)
    paragraph_char_end: int = Field(ge=1)
    raw_text: str = Field(min_length=1)
    clean_text: str = Field(min_length=1)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    cleaned_page_ids: tuple[str, ...] = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ChunkingResult(ChunkingModel):
    document_id: str = Field(min_length=1)
    source_file_id: str = Field(min_length=1)
    policy: ChunkingPolicy
    structure: tuple[StructureNode, ...]
    chunks: tuple[StructuredChunk, ...]


class ChunkSet(ChunkingResult):
    id: str = Field(min_length=1)
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_by: str = Field(min_length=1)
    generated_at: datetime


class StructuredChunkRepository(Protocol):
    async def save(self, chunk_set: ChunkSet) -> None: ...

    async def get(self, source_file_id: str, split_version: str) -> ChunkSet | None: ...

    async def list_versions(self, source_file_id: str) -> list[ChunkSet]: ...

    async def list_all(self) -> list[ChunkSet]: ...


def chunk_cleaned_pages(
    *,
    document_id: str,
    source_file_id: str,
    pages: tuple[ChunkSourcePage, ...],
    policy: ChunkingPolicy,
) -> ChunkingResult:
    ordered_pages = tuple(sorted(pages, key=lambda page: page.page_number))
    paragraphs: list[_Paragraph] = []
    volumes: list[_NodeBuilder] = []
    current_volume: _NodeBuilder | None = None
    current_item: _NodeBuilder | None = None
    paragraph_fragments: list[_PageFragment] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_fragments
        text = "".join(fragment.text for fragment in paragraph_fragments).strip()
        if text and paragraph_fragments:
            paragraphs.append(
                _Paragraph(
                    clean_text=text,
                    fragments=tuple(paragraph_fragments),
                    volume=current_volume.title if current_volume else None,
                    item=current_item.title if current_item else None,
                )
            )
        paragraph_fragments = []

    for page in ordered_pages:
        for line in _clean_lines(page.clean_text):
            stripped = line.text
            if not stripped:
                flush_paragraph()
                continue
            if _VOLUME_HEADING.fullmatch(stripped):
                flush_paragraph()
                current_volume = _NodeBuilder(kind="volume", title=stripped, page_start=page.page_number, page_end=page.page_number)
                volumes.append(current_volume)
                current_item = None
                continue
            if _ITEM_HEADING.fullmatch(stripped):
                flush_paragraph()
                if current_volume is None:
                    current_volume = _NodeBuilder(kind="volume", title="未标卷", page_start=page.page_number, page_end=page.page_number)
                    volumes.append(current_volume)
                current_item = _NodeBuilder(kind="item", title=stripped, page_start=page.page_number, page_end=page.page_number)
                current_volume.children.append(current_item)
                continue
            paragraph_start = sum(len(fragment.text) for fragment in paragraph_fragments)
            paragraph_fragments.append(
                _PageFragment(
                    page=page,
                    text=stripped,
                    clean_start=line.clean_start,
                    clean_end=line.clean_end,
                    paragraph_start=paragraph_start,
                    paragraph_end=paragraph_start + len(stripped),
                )
            )
        if paragraph_fragments and _PARAGRAPH_END.search(paragraph_fragments[-1].text):
            flush_paragraph()
        if current_volume is not None:
            current_volume.page_end = page.page_number
        if current_item is not None:
            current_item.page_end = page.page_number

    flush_paragraph()

    chunks_list: list[StructuredChunk] = []
    for paragraph_index, paragraph in enumerate(paragraphs):
        for window_start, window_end in _window_ranges(len(paragraph.clean_text), policy):
            chunks_list.append(
                _make_chunk(
                    document_id=document_id,
                    source_file_id=source_file_id,
                    policy=policy,
                    paragraph=paragraph,
                    chunk_index=len(chunks_list),
                    paragraph_index=paragraph_index,
                    paragraph_char_start=window_start,
                    paragraph_char_end=window_end,
                )
            )
    chunks = tuple(chunks_list)
    structure = tuple(_build_node(source_file_id, policy, node, index) for index, node in enumerate(volumes))
    return ChunkingResult(
        document_id=document_id,
        source_file_id=source_file_id,
        policy=policy,
        structure=structure,
        chunks=chunks,
    )


@dataclass
class _Paragraph:
    clean_text: str
    fragments: tuple[_PageFragment, ...]
    volume: str | None
    item: str | None


@dataclass(frozen=True)
class _PageFragment:
    page: ChunkSourcePage
    text: str
    clean_start: int
    clean_end: int
    paragraph_start: int
    paragraph_end: int


@dataclass(frozen=True)
class _CleanLine:
    text: str
    clean_start: int
    clean_end: int


@dataclass
class _NodeBuilder:
    kind: Literal["volume", "item"]
    title: str
    page_start: int
    page_end: int
    children: list[_NodeBuilder] = field(default_factory=list)


def _make_chunk(
    *,
    document_id: str,
    source_file_id: str,
    policy: ChunkingPolicy,
    paragraph: _Paragraph,
    chunk_index: int,
    paragraph_index: int,
    paragraph_char_start: int,
    paragraph_char_end: int,
) -> StructuredChunk:
    clean_text = paragraph.clean_text[paragraph_char_start:paragraph_char_end]
    fragments = [fragment for fragment in paragraph.fragments if fragment.paragraph_end > paragraph_char_start and fragment.paragraph_start < paragraph_char_end]
    raw_parts = []
    for fragment in fragments:
        fragment_start = max(paragraph_char_start, fragment.paragraph_start) - fragment.paragraph_start
        fragment_end = min(paragraph_char_end, fragment.paragraph_end) - fragment.paragraph_start
        raw_parts.append(
            _project_clean_range_to_raw(
                raw_text=fragment.page.raw_text,
                clean_text=fragment.page.clean_text,
                clean_start=fragment.clean_start + fragment_start,
                clean_end=fragment.clean_start + fragment_end,
            )
        )
    raw_text = "".join(raw_parts)
    if not raw_text.strip():
        raw_text = "\n".join(
            dict.fromkeys(
                fragment.page.raw_text
                for fragment in fragments
                if fragment.page.raw_text.strip()
            )
        )
    page_start = min(fragment.page.page_number for fragment in fragments)
    page_end = max(fragment.page.page_number for fragment in fragments)
    cleaned_page_ids = tuple(dict.fromkeys(fragment.page.cleaned_page_id for fragment in fragments))
    content_sha256 = _sha256(clean_text)
    identity = "\x1f".join(
        (
            source_file_id,
            policy.model_dump_json(),
            str(chunk_index),
            paragraph.volume or "",
            paragraph.item or "",
            str(page_start),
            str(page_end),
            content_sha256,
        )
    )
    return StructuredChunk(
        id=f"chunk-{_sha256(identity)}",
        document_id=document_id,
        source_file_id=source_file_id,
        split_version=policy.split_version,
        chunk_index=chunk_index,
        volume=paragraph.volume,
        item=paragraph.item,
        paragraph_index=paragraph_index,
        paragraph_char_start=paragraph_char_start,
        paragraph_char_end=paragraph_char_end,
        raw_text=raw_text,
        clean_text=clean_text,
        page_start=page_start,
        page_end=page_end,
        cleaned_page_ids=cleaned_page_ids,
        content_sha256=content_sha256,
    )


def _build_node(source_file_id: str, policy: ChunkingPolicy, node: _NodeBuilder, index: int) -> StructureNode:
    identity = "\x1f".join((source_file_id, policy.model_dump_json(), node.kind, str(index), node.title))
    node_id = f"structure-{_sha256(identity)}"
    return StructureNode(
        id=node_id,
        kind=node.kind,
        title=node.title,
        page_start=node.page_start,
        page_end=node.page_end,
        children=tuple(_build_node(source_file_id, policy, child, child_index) for child_index, child in enumerate(node.children)),
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _window_ranges(length: int, policy: ChunkingPolicy) -> tuple[tuple[int, int], ...]:
    if length <= policy.max_characters:
        return ((0, length),)
    ranges = []
    start = 0
    step = policy.max_characters - policy.overlap_characters
    while start < length:
        end = min(start + policy.max_characters, length)
        ranges.append((start, end))
        if end == length:
            break
        start += step
    return tuple(ranges)


def _clean_lines(text: str) -> tuple[_CleanLine, ...]:
    lines = []
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        without_break = raw_line.rstrip("\r\n")
        stripped = without_break.strip()
        leading = len(without_break) - len(without_break.lstrip())
        start = offset + leading
        lines.append(_CleanLine(text=stripped, clean_start=start, clean_end=start + len(stripped)))
        offset += len(raw_line)
    if not lines:
        lines.append(_CleanLine(text=text.strip(), clean_start=0, clean_end=len(text.strip())))
    return tuple(lines)


def _project_clean_range_to_raw(*, raw_text: str, clean_text: str, clean_start: int, clean_end: int) -> str:
    parts = []
    for tag, raw_start, raw_end, mapped_start, mapped_end in SequenceMatcher(a=raw_text, b=clean_text, autojunk=False).get_opcodes():
        if tag == "equal":
            start = max(clean_start, mapped_start)
            end = min(clean_end, mapped_end)
            if start < end:
                parts.append(raw_text[raw_start + start - mapped_start : raw_start + end - mapped_start])
        elif tag == "replace" and mapped_start < clean_end and mapped_end > clean_start:
            if raw_end - raw_start == mapped_end - mapped_start:
                start = max(clean_start, mapped_start)
                end = min(clean_end, mapped_end)
                parts.append(raw_text[raw_start + start - mapped_start : raw_start + end - mapped_start])
            else:
                parts.append(raw_text[raw_start:raw_end])
        elif tag == "delete" and clean_start < mapped_start < clean_end:
            parts.append(raw_text[raw_start:raw_end])
    return "".join(parts)


_NUMERAL = r"[〇零一二三四五六七八九十百千0-9]+"
_VOLUME_HEADING = re.compile(rf"(?:第{_NUMERAL}卷|卷{_NUMERAL})(?:\s+.*)?")
_ITEM_HEADING = re.compile(rf"(?:第{_NUMERAL}目|目{_NUMERAL})(?:\s+.*)?")
_PARAGRAPH_END = re.compile(r"[。！？；.!?;]\s*$")
