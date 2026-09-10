from __future__ import annotations

import base64
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from wu_culture.parsing import DocumentParseError, DocumentParseRequest, parse_document


def _text_pdf(*pages: str, metadata: dict[str, str] | None = None) -> bytes:
    objects: list[bytes] = []
    page_ids: list[int] = []
    for page_number, text in enumerate(pages, start=1):
        page_id = 3 + (page_number - 1) * 2
        content_id = page_id + 1
        page_ids.append(page_id)
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii")
        objects.extend(
            [
                (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {3 + len(pages) * 2} 0 R >> >> /Contents {content_id} 0 R >>").encode("ascii"),
                b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
            ]
        )

    catalog_and_pages = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] /Count {len(page_ids)} >>".encode("ascii"),
    ]
    all_objects = catalog_and_pages + objects + [b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    info_id: int | None = None
    if metadata:
        info_id = len(all_objects) + 1
        entries = " ".join(f"/{key} ({value})" for key, value in metadata.items())
        all_objects.append(f"<< {entries} >>".encode("ascii"))
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, body in enumerate(all_objects, start=1):
        offsets.append(len(result))
        result.extend(f"{object_id} 0 obj\n".encode("ascii"))
        result.extend(body)
        result.extend(b"\nendobj\n")
    xref_offset = len(result)
    result.extend(f"xref\n0 {len(all_objects) + 1}\n".encode("ascii"))
    result.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    info_reference = f" /Info {info_id} 0 R" if info_id is not None else ""
    result.extend(f"trailer\n<< /Size {len(all_objects) + 1} /Root 1 0 R{info_reference} >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return bytes(result)


def test_text_pdf_preserves_page_text_and_source_page_numbers():
    result = parse_document(
        DocumentParseRequest(
            filename="mudu.pdf",
            mime_type="application/pdf",
            content=_text_pdf("Mudu page one", "Mudu page two"),
        )
    )

    assert result.page_count == 2
    assert [block.text for block in result.blocks] == ["Mudu page one", "Mudu page two"]
    assert [block.page_number for block in result.blocks] == [1, 2]
    assert result.metadata["pagination"] == "physical"


def _docx(document_xml: str, *, footnotes_xml: str | None = None, core_xml: str | None = None) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        archive.writestr("word/document.xml", document_xml)
        if footnotes_xml is not None:
            archive.writestr("word/footnotes.xml", footnotes_xml)
        if core_xml is not None:
            archive.writestr("docProps/core.xml", core_xml)
    return output.getvalue()


def test_docx_preserves_paragraph_table_footnote_and_explicit_page_structure():
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    document_xml = f"""
    <w:document xmlns:w="{namespace}"><w:body>
      <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>木渎小志</w:t></w:r></w:p>
      <w:p><w:r><w:t>首段</w:t></w:r><w:r><w:footnoteReference w:id="2"/></w:r></w:p>
      <w:tbl>
        <w:tr><w:tc><w:p><w:r><w:t>地点</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>年代</w:t></w:r></w:p></w:tc></w:tr>
        <w:tr><w:tc><w:p><w:r><w:t>木渎</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>明</w:t></w:r></w:p></w:tc></w:tr>
      </w:tbl>
      <w:p><w:r><w:br w:type="page"/><w:t>次页</w:t></w:r></w:p>
    </w:body></w:document>
    """
    footnotes_xml = f"""
    <w:footnotes xmlns:w="{namespace}">
      <w:footnote w:id="2"><w:p><w:r><w:t>脚注原文</w:t></w:r></w:p></w:footnote>
    </w:footnotes>
    """

    result = parse_document(
        DocumentParseRequest(
            filename="mudu.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            content=_docx(document_xml, footnotes_xml=footnotes_xml),
        )
    )

    assert [(block.block_type, block.page_number, block.text) for block in result.blocks] == [
        ("heading", 1, "木渎小志"),
        ("paragraph", 1, "首段[^2]"),
        ("table", 1, "地点 | 年代\n木渎 | 明"),
        ("paragraph", 2, "次页"),
        ("footnote", 1, "[^2] 脚注原文"),
    ]
    assert result.page_count == 2


def test_txt_detects_chinese_encoding_and_preserves_paragraphs():
    text = "木渎古镇沿革。香溪水道连接太湖，地方志记载街巷桥梁。\n\n第二段记录市镇变迁。"

    result = parse_document(
        DocumentParseRequest(
            filename="mudu.txt",
            mime_type="text/plain",
            content=text.encode("gb18030"),
        )
    )

    assert [block.text for block in result.blocks] == [
        "木渎古镇沿革。香溪水道连接太湖，地方志记载街巷桥梁。",
        "第二段记录市镇变迁。",
    ]
    assert result.metadata == {"encoding": "gb18030", "pagination": "logical"}
    assert result.page_count == 1


def test_markdown_marks_headings_tables_and_footnotes_without_losing_order():
    content = """# 木渎沿革

正文引用脚注[^1]。

| 地点 | 年代 |
| --- | --- |
| 木渎 | 明代 |

[^1]: 《木渎小志》卷一。
"""

    result = parse_document(
        DocumentParseRequest(
            filename="mudu.md",
            mime_type="text/markdown",
            content=content.encode(),
        )
    )

    assert [(block.block_type, block.text) for block in result.blocks] == [
        ("heading", "木渎沿革"),
        ("paragraph", "正文引用脚注[^1]。"),
        ("table", "| 地点 | 年代 |\n| --- | --- |\n| 木渎 | 明代 |"),
        ("footnote", "[^1] 《木渎小志》卷一。"),
    ]
    assert result.metadata == {"encoding": "utf-8-sig", "pagination": "logical"}


def test_corrupt_pdf_reports_stable_invalid_pdf_error():
    with pytest.raises(DocumentParseError) as caught:
        parse_document(
            DocumentParseRequest(
                filename="broken.pdf",
                mime_type="application/pdf",
                content=b"%PDF-1.7\nnot a valid PDF",
            )
        )

    assert caught.value.code == "invalid_pdf"


def test_pdf_without_text_layer_is_deferred_to_ocr():
    with pytest.raises(DocumentParseError) as caught:
        parse_document(
            DocumentParseRequest(
                filename="scan.pdf",
                mime_type="application/pdf",
                content=_text_pdf(""),
            )
        )

    assert caught.value.code == "no_extractable_text"


def test_password_protected_pdf_reports_explicit_error():
    encrypted_pdf = base64.b64decode(
        "JVBERi0xLjMKJeLjz9MKMSAwIG9iago8PAovUHJvZHVjZXIgPDM1YzY5Y2I1ZTA+Cj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9UeXBlIC9QYWdlcwovQ291bnQgMQovS2lkcyBbIDQgMCBSIF0KPj4KZW5kb2JqCjMgMCBvYmoKPDwKL1R5cGUgL0NhdGFsb2cKL1BhZ2VzIDIgMCBSCj4+CmVuZG9iago0IDAgb2JqCjw8Ci9UeXBlIC9QYWdlCi9SZXNvdXJjZXMgPDwKPj4KL01lZGlhQm94IFsgMC4wIDAuMCA3MiA3MiBdCi9QYXJlbnQgMiAwIFIKPj4KZW5kb2JqCjUgMCBvYmoKPDwKL1YgMgovUiAzCi9MZW5ndGggMTI4Ci9QIDQyOTQ5NjcyOTIKL0ZpbHRlciAvU3RhbmRhcmQKL08gPDBlNTIyOTI1YTNlNGU4NzRjM2NmYWNiZWY1MTFhNzNhYzRlYzJiZDg2NWRjZDNkNDYyNzYxNDkxN2FiZmQ3ZTQ+Ci9VIDxiNjIzNzAzMjY3YTBjODJlMzliYmIwMTc0YTVlODUzNDI4YmY0ZTVlNGU3NThhNDE2NDAwNGU1NmZmZmEwMTA4Pgo+PgplbmRvYmoKeHJlZgowIDYKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDE1IDAwMDAwIG4gCjAwMDAwMDAwNTkgMDAwMDAgbiAKMDAwMDAwMDExOCAwMDAwMCBuIAowMDAwMDAwMTY3IDAwMDAwIG4gCjAwMDAwMDAyNTkgMDAwMDAgbiAKdHJhaWxlcgo8PAovU2l6ZSA2Ci9Sb290IDMgMCBSCi9JbmZvIDEgMCBSCi9JRCBbIDw2NDY2NjM2MTY2MzUzNDMyMzczOTMwMzMzMjMwMzY2NDY0MzEzMTM0MzQzMTY0MzA2MjM1NjI2MTM5MzYzMTYyPiA8NjQ2NjM2MTY2NjM1MzQzMjM3MzkzMDMzMzIzMDM2NjQ2NDMxMzEzNDM0MzE2NDMwNjIzNTYyNjEzOTM2MzE2Mj4gXQovRW5jcnlwdCA1IDAgUgo+PgpzdGFydHhyZWYKNDc0CiUlRU9GCg=="
    )

    with pytest.raises(DocumentParseError) as caught:
        parse_document(
            DocumentParseRequest(
                filename="protected.pdf",
                mime_type="application/pdf",
                content=encrypted_pdf,
            )
        )

    assert caught.value.code == "password_protected_pdf"


def test_pdf_reads_declared_metadata_without_guessing_from_text():
    result = parse_document(
        DocumentParseRequest(
            filename="metadata.pdf",
            mime_type="application/pdf",
            content=_text_pdf("Body title is different", metadata={"Title": "Mudu Gazetteer", "Author": "Local Archive"}),
        )
    )

    assert result.metadata == {
        "pagination": "physical",
        "title": "Mudu Gazetteer",
        "author": "Local Archive",
    }


def test_corrupt_docx_reports_stable_invalid_docx_error():
    with pytest.raises(DocumentParseError) as caught:
        parse_document(
            DocumentParseRequest(
                filename="broken.docx",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                content=b"PK\x03\x04broken",
            )
        )

    assert caught.value.code == "invalid_docx"


def test_docx_reads_declared_core_metadata_without_guessing_from_body():
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    core_xml = """
    <cp:coreProperties
      xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
      xmlns:dc="http://purl.org/dc/elements/1.1/"
      xmlns:dcterms="http://purl.org/dc/terms/">
      <dc:title>木渎小志数字本</dc:title>
      <dc:creator>苏州地方文献馆</dc:creator>
      <dcterms:created>2026-07-01T08:00:00Z</dcterms:created>
      <dcterms:modified>2026-07-02T09:30:00Z</dcterms:modified>
    </cp:coreProperties>
    """
    content = _docx(
        f'<w:document xmlns:w="{namespace}"><w:body><w:p><w:r><w:t>正文</w:t></w:r></w:p></w:body></w:document>',
        core_xml=core_xml,
    )

    result = parse_document(
        DocumentParseRequest(
            filename="metadata.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            content=content,
        )
    )

    assert result.metadata == {
        "pagination": "explicit",
        "title": "木渎小志数字本",
        "author": "苏州地方文献馆",
        "created_at": "2026-07-01T08:00:00Z",
        "modified_at": "2026-07-02T09:30:00Z",
    }


def test_binary_text_reports_unknown_encoding():
    with pytest.raises(DocumentParseError) as caught:
        parse_document(
            DocumentParseRequest(
                filename="garbled.txt",
                mime_type="text/plain",
                content=bytes([0, 129, 0, 255]) * 32,
            )
        )

    assert caught.value.code == "text_encoding_unknown"
