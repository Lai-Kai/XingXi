from __future__ import annotations

import hashlib
from io import BytesIO

from PIL import Image

from .service import OcrPageImage


def render_ocr_pages(*, filename: str, mime_type: str, content: bytes, dpi: int = 150) -> tuple[OcrPageImage, ...]:
    if mime_type in {"image/png", "image/jpeg"}:
        with Image.open(BytesIO(content)) as source:
            source.load()
            image = source.convert("RGB")
        rendered = _encode_png(image)
        return (
            OcrPageImage(
                page_number=1,
                content=rendered,
                width=image.width,
                height=image.height,
                sha256=hashlib.sha256(rendered).hexdigest(),
            ),
        )
    if mime_type != "application/pdf":
        raise ValueError(f"Unsupported OCR document type: {mime_type}")

    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(content)
    try:
        pages: list[OcrPageImage] = []
        for page_index in range(len(document)):
            page = document[page_index]
            try:
                bitmap = page.render(scale=dpi / 72)
                try:
                    image = bitmap.to_pil()
                    rendered = _encode_png(image)
                finally:
                    bitmap.close()
            finally:
                page.close()
            pages.append(
                OcrPageImage(
                    page_number=page_index + 1,
                    content=rendered,
                    width=image.width,
                    height=image.height,
                    sha256=hashlib.sha256(rendered).hexdigest(),
                )
            )
        return tuple(pages)
    finally:
        document.close()


def _encode_png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
