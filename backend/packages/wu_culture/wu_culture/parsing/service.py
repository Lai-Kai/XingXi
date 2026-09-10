from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO
from typing import Literal
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from pydantic import BaseModel, ConfigDict, Field


class DocumentParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    content: bytes = Field(min_length=1)


class ParsedBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_type: Literal["paragraph", "heading", "table", "footnote"]
    page_number: int = Field(ge=1)
    block_index: int = Field(ge=0)
    text: str = Field(min_length=1)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ParsedDocumentContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parser_name: str = Field(min_length=1)
    parser_version: str = Field(min_length=1)
    page_count: int = Field(ge=1)
    text: str = Field(min_length=1)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    blocks: tuple[ParsedBlock, ...]


class ParsedDocument(ParsedDocumentContent):
    id: str = Field(min_length=1)
    source_file_id: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    parsed_at: datetime


class DocumentParseError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def parse_document(request: DocumentParseRequest) -> ParsedDocumentContent:
    if request.mime_type == "application/pdf":
        return _parse_pdf(request.content)
    if request.mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _parse_docx(request.content)
    if request.mime_type == "text/plain":
        return _parse_plain_text(request.content)
    if request.mime_type == "text/markdown":
        return _parse_markdown(request.content)
    raise DocumentParseError("unsupported_document_type", "Unsupported document type")


def _parse_pdf(content: bytes) -> ParsedDocumentContent:
    import pypdfium2 as pdfium

    try:
        document = pdfium.PdfDocument(content)
    except pdfium.PdfiumError as exc:
        if exc.err_code == pdfium.raw.FPDF_ERR_PASSWORD:
            raise DocumentParseError("password_protected_pdf", "PDF requires a password") from exc
        raise DocumentParseError("invalid_pdf", "PDF is damaged or invalid") from exc
    try:
        blocks: list[ParsedBlock] = []
        for page_number in range(1, len(document) + 1):
            page = document[page_number - 1]
            try:
                text_page = page.get_textpage()
                try:
                    text = text_page.get_text_range().strip()
                finally:
                    text_page.close()
            finally:
                page.close()
            if text:
                blocks.append(
                    ParsedBlock(
                        block_type="paragraph",
                        page_number=page_number,
                        block_index=len(blocks),
                        text=text,
                    )
                )
        joined = "\n\n".join(block.text for block in blocks)
        if not joined:
            raise DocumentParseError("no_extractable_text", "PDF has no extractable text layer")
        metadata: dict[str, str | int | float | bool | None] = {"pagination": "physical"}
        declared_metadata = document.get_metadata_dict(skip_empty=True)
        metadata_names = {
            "Title": "title",
            "Author": "author",
            "Subject": "subject",
            "Keywords": "keywords",
            "Creator": "creator",
            "Producer": "producer",
            "CreationDate": "created_at",
            "ModDate": "modified_at",
        }
        for source_name, target_name in metadata_names.items():
            value = declared_metadata.get(source_name)
            if value and value.strip():
                metadata[target_name] = value.strip()
        return ParsedDocumentContent(
            parser_name="pdfium",
            parser_version="1",
            page_count=len(document),
            text=joined,
            metadata=metadata,
            blocks=tuple(blocks),
        )
    finally:
        document.close()


_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_WORD = f"{{{_WORD_NAMESPACE}}}"


def _parse_docx(content: bytes) -> ParsedDocumentContent:
    try:
        with ZipFile(BytesIO(content)) as archive:
            document_root = ElementTree.fromstring(archive.read("word/document.xml"))
            footnotes_root = ElementTree.fromstring(archive.read("word/footnotes.xml")) if "word/footnotes.xml" in archive.namelist() else None
            core_root = ElementTree.fromstring(archive.read("docProps/core.xml")) if "docProps/core.xml" in archive.namelist() else None
    except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise DocumentParseError("invalid_docx", "DOCX is damaged or invalid") from exc

    body = document_root.find(f"{_WORD}body")
    if body is None:
        raise DocumentParseError("invalid_docx", "DOCX document body is missing")

    blocks: list[ParsedBlock] = []
    footnote_pages: dict[str, int] = {}
    page_number = 1
    for child in body:
        if child.tag == f"{_WORD}p":
            segments, page_number = _docx_paragraph_segments(child, page_number, footnote_pages)
            style = child.find(f"{_WORD}pPr/{_WORD}pStyle")
            style_name = style.get(f"{_WORD}val", "") if style is not None else ""
            block_type: Literal["paragraph", "heading"] = "heading" if style_name.lower().startswith("heading") else "paragraph"
            for segment_page, text in segments:
                blocks.append(
                    ParsedBlock(
                        block_type=block_type,
                        page_number=segment_page,
                        block_index=len(blocks),
                        text=text,
                        metadata={"style": style_name} if style_name else {},
                    )
                )
        elif child.tag == f"{_WORD}tbl":
            rows = []
            for row in child.findall(f"{_WORD}tr"):
                cells = ["".join(node.text or "" for node in cell.iter(f"{_WORD}t")).strip() for cell in row.findall(f"{_WORD}tc")]
                rows.append(" | ".join(cells))
            table_text = "\n".join(row for row in rows if row.strip())
            if table_text:
                blocks.append(
                    ParsedBlock(
                        block_type="table",
                        page_number=page_number,
                        block_index=len(blocks),
                        text=table_text,
                    )
                )

    if footnotes_root is not None:
        for footnote in footnotes_root.findall(f"{_WORD}footnote"):
            footnote_id = footnote.get(f"{_WORD}id", "")
            if footnote_id not in footnote_pages:
                continue
            text = "".join(node.text or "" for node in footnote.iter(f"{_WORD}t")).strip()
            if text:
                blocks.append(
                    ParsedBlock(
                        block_type="footnote",
                        page_number=footnote_pages[footnote_id],
                        block_index=len(blocks),
                        text=f"[^{footnote_id}] {text}",
                        metadata={"footnote_id": footnote_id},
                    )
                )

    metadata: dict[str, str | int | float | bool | None] = {"pagination": "explicit"}
    if core_root is not None:
        core_fields = {
            "title": "{http://purl.org/dc/elements/1.1/}title",
            "author": "{http://purl.org/dc/elements/1.1/}creator",
            "created_at": "{http://purl.org/dc/terms/}created",
            "modified_at": "{http://purl.org/dc/terms/}modified",
        }
        for name, tag in core_fields.items():
            value = core_root.findtext(tag)
            if value and value.strip():
                metadata[name] = value.strip()

    return ParsedDocumentContent(
        parser_name="openxml",
        parser_version="1",
        page_count=max((block.page_number for block in blocks), default=1),
        text="\n\n".join(block.text for block in blocks),
        metadata=metadata,
        blocks=tuple(blocks),
    )


def _docx_paragraph_segments(
    paragraph: ElementTree.Element,
    page_number: int,
    footnote_pages: dict[str, int],
) -> tuple[list[tuple[int, str]], int]:
    segments: list[tuple[int, str]] = []
    parts: list[str] = []
    segment_page = page_number
    for node in paragraph.iter():
        if node.tag == f"{_WORD}t":
            parts.append(node.text or "")
        elif node.tag == f"{_WORD}tab":
            parts.append("\t")
        elif node.tag in {f"{_WORD}br", f"{_WORD}lastRenderedPageBreak"} and (node.tag == f"{_WORD}lastRenderedPageBreak" or node.get(f"{_WORD}type") == "page"):
            text = "".join(parts).strip()
            if text:
                segments.append((segment_page, text))
            parts = []
            page_number += 1
            segment_page = page_number
        elif node.tag == f"{_WORD}footnoteReference":
            footnote_id = node.get(f"{_WORD}id", "")
            if footnote_id:
                parts.append(f"[^{footnote_id}]")
                footnote_pages.setdefault(footnote_id, segment_page)
    text = "".join(parts).strip()
    if text:
        segments.append((segment_page, text))
    return segments, page_number


def _parse_plain_text(content: bytes) -> ParsedDocumentContent:
    text, encoding = _decode_text(content)
    paragraphs = [part.strip() for part in re.split(r"(?:\r?\n){2,}", text) if part.strip()]
    blocks = tuple(
        ParsedBlock(
            block_type="paragraph",
            page_number=1,
            block_index=index,
            text=paragraph,
        )
        for index, paragraph in enumerate(paragraphs)
    )
    return ParsedDocumentContent(
        parser_name="plain-text",
        parser_version="1",
        page_count=1,
        text="\n\n".join(block.text for block in blocks),
        metadata={"encoding": encoding, "pagination": "logical"},
        blocks=blocks,
    )


def _decode_text(content: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            decoded = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if encoding == "utf-16" and not content.startswith((b"\xff\xfe", b"\xfe\xff")):
            continue
        return decoded, encoding

    from charset_normalizer import from_bytes

    match = from_bytes(content).best()
    if match is None or match.chaos > 0.3:
        raise DocumentParseError("text_encoding_unknown", "Text encoding could not be determined")
    return str(match), match.encoding.lower()


def _parse_markdown(content: bytes) -> ParsedDocumentContent:
    text, encoding = _decode_text(content)
    lines = text.splitlines()
    blocks: list[ParsedBlock] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        heading = re.fullmatch(r"(#{1,6})\s+(.+)", line)
        if heading:
            blocks.append(
                ParsedBlock(
                    block_type="heading",
                    page_number=1,
                    block_index=len(blocks),
                    text=heading.group(2).strip(),
                    metadata={"level": len(heading.group(1))},
                )
            )
            index += 1
            continue
        footnote = re.fullmatch(r"\[\^([^]]+)]\s*:\s*(.+)", line)
        if footnote:
            blocks.append(
                ParsedBlock(
                    block_type="footnote",
                    page_number=1,
                    block_index=len(blocks),
                    text=f"[^{footnote.group(1)}] {footnote.group(2).strip()}",
                    metadata={"footnote_id": footnote.group(1)},
                )
            )
            index += 1
            continue
        if line.startswith("|") and line.endswith("|"):
            table_lines = [line]
            index += 1
            while index < len(lines):
                table_line = lines[index].strip()
                if not (table_line.startswith("|") and table_line.endswith("|")):
                    break
                table_lines.append(table_line)
                index += 1
            blocks.append(
                ParsedBlock(
                    block_type="table",
                    page_number=1,
                    block_index=len(blocks),
                    text="\n".join(table_lines),
                    metadata={"format": "markdown"},
                )
            )
            continue

        paragraph_lines = [line]
        index += 1
        while index < len(lines) and lines[index].strip():
            paragraph_lines.append(lines[index].strip())
            index += 1
        blocks.append(
            ParsedBlock(
                block_type="paragraph",
                page_number=1,
                block_index=len(blocks),
                text="\n".join(paragraph_lines),
            )
        )

    return ParsedDocumentContent(
        parser_name="markdown",
        parser_version="1",
        page_count=1,
        text="\n\n".join(block.text for block in blocks),
        metadata={"encoding": encoding, "pagination": "logical"},
        blocks=tuple(blocks),
    )
