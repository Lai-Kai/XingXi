from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO

import pytest
from PIL import Image
from wu_culture.ocr import (
    OcrBoundingBox,
    OcrPageImage,
    OcrPageStatus,
    OcrProviderPage,
    OcrRegion,
    OcrService,
    render_ocr_pages,
)


def _blank_pdf(page_count: int) -> bytes:
    page_ids = [3 + index for index in range(page_count)]
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] /Count {page_count} >>".encode(),
        *(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 144] >>" for _ in page_ids),
    ]
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(f"{object_id} 0 obj\n".encode())
        result.extend(body)
        result.extend(b"\nendobj\n")
    xref_offset = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    return bytes(result)


class _PartiallyFailingProvider:
    name = "test-ocr"
    model = "test-model"

    async def recognize(self, page: OcrPageImage, *, languages: tuple[str, ...]) -> OcrProviderPage:
        if page.page_number == 2:
            raise RuntimeError("synthetic page failure")
        return OcrProviderPage(
            raw_text="木渎",
            mean_confidence=0.96,
            rotation_degrees=0,
            regions=(
                OcrRegion(
                    text="木渎",
                    confidence=0.96,
                    bounding_box=OcrBoundingBox(x=0.1, y=0.2, width=0.3, height=0.1),
                ),
            ),
        )


class _LowConfidenceProvider:
    name = "test-ocr"
    model = "test-model"

    async def recognize(self, page: OcrPageImage, *, languages: tuple[str, ...]) -> OcrProviderPage:
        return OcrProviderPage(
            raw_text="待校对文本",
            mean_confidence=0.79,
            rotation_degrees=0,
            regions=(
                OcrRegion(
                    text="待校对文本",
                    confidence=0.79,
                    bounding_box=OcrBoundingBox(x=0.05, y=0.1, width=0.4, height=0.08),
                ),
            ),
        )


def test_page_failure_does_not_discard_successful_siblings():
    service = OcrService(
        _PartiallyFailingProvider(),
        languages=("zh-Hans", "zh-Hant"),
        review_confidence_threshold=0.8,
        max_concurrency=2,
    )
    pages = (
        OcrPageImage(page_number=1, content=b"page-one", width=1000, height=1500, sha256="a" * 64),
        OcrPageImage(page_number=2, content=b"page-two", width=1000, height=1500, sha256="b" * 64),
    )

    results = asyncio.run(service.recognize_pages(source_file_id="source-file-1", pages=pages))

    assert [result.status for result in results] == [OcrPageStatus.COMPLETED, OcrPageStatus.FAILED]
    assert results[0].raw_text == "木渎"
    assert results[0].regions[0].bounding_box.model_dump() == {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1}
    assert results[1].error_code == "ocr_page_failed"
    assert results[1].error_message == "synthetic page failure"


def test_low_confidence_page_requires_human_review():
    service = OcrService(
        _LowConfidenceProvider(),
        languages=("zh-Hans",),
        review_confidence_threshold=0.8,
        max_concurrency=1,
    )
    page = OcrPageImage(page_number=1, content=b"page-one", width=1000, height=1500, sha256="a" * 64)

    (result,) = asyncio.run(service.recognize_pages(source_file_id="source-file-1", pages=(page,)))

    assert result.status is OcrPageStatus.REVIEW_REQUIRED
    assert result.raw_text == "待校对文本"
    assert result.mean_confidence == 0.79
    assert result.error_code is None


def test_pdf_renderer_returns_one_hashed_png_per_physical_page():
    pages = render_ocr_pages(filename="scan.pdf", mime_type="application/pdf", content=_blank_pdf(2))

    assert [page.page_number for page in pages] == [1, 2]
    assert all(page.content.startswith(b"\x89PNG\r\n\x1a\n") for page in pages)
    assert all((page.width, page.height) == (150, 300) for page in pages)
    assert [page.sha256 for page in pages] == [hashlib.sha256(page.content).hexdigest() for page in pages]


@pytest.mark.parametrize(("source_format", "mime_type"), [("PNG", "image/png"), ("JPEG", "image/jpeg")])
def test_image_renderer_normalizes_supported_images_to_one_png_page(source_format: str, mime_type: str):
    source = BytesIO()
    Image.new("RGB", (16, 8), color="white").save(source, format=source_format)

    (page,) = render_ocr_pages(filename=f"scan.{source_format.lower()}", mime_type=mime_type, content=source.getvalue())

    assert page.page_number == 1
    assert page.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert (page.width, page.height) == (16, 8)
    assert page.sha256 == hashlib.sha256(page.content).hexdigest()
