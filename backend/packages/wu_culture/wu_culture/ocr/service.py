from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OcrModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OcrBoundingBox(OcrModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def stay_within_page(self) -> OcrBoundingBox:
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("bounding box must stay within normalized page coordinates")
        return self


class OcrRegion(OcrModel):
    text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    bounding_box: OcrBoundingBox


class OcrPageImage(OcrModel):
    page_number: int = Field(ge=1)
    content: bytes = Field(min_length=1)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    object_key: str | None = None


class OcrProviderPage(OcrModel):
    raw_text: str = Field(min_length=1)
    mean_confidence: float = Field(ge=0, le=1)
    rotation_degrees: int
    regions: tuple[OcrRegion, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_rotation(self) -> OcrProviderPage:
        if self.rotation_degrees not in {0, 90, 180, 270}:
            raise ValueError("rotation_degrees must be 0, 90, 180, or 270")
        return self


class OcrPageStatus(StrEnum):
    COMPLETED = "completed"
    REVIEW_REQUIRED = "review_required"
    FAILED = "failed"


class OcrPageAttempt(OcrModel):
    id: str = Field(min_length=1)
    source_file_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    attempt_number: int = Field(ge=1)
    folio_label: str | None = Field(default=None, min_length=1)
    page_image_object_key: str | None = None
    image_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    image_width: int | None = Field(default=None, ge=1)
    image_height: int | None = Field(default=None, ge=1)
    provider_name: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    languages: tuple[str, ...] = Field(min_length=1)
    status: OcrPageStatus
    raw_text: str | None = None
    mean_confidence: float | None = Field(default=None, ge=0, le=1)
    rotation_degrees: int = 0
    regions: tuple[OcrRegion, ...] = ()
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_optional_image_metadata(self) -> OcrPageAttempt:
        values = (self.image_sha256, self.image_width, self.image_height)
        if any(value is None for value in values) and any(value is not None for value in values):
            raise ValueError("image_sha256, image_width, and image_height must be provided together")
        return self


class OcrProvider(Protocol):
    name: str
    model: str

    async def recognize(self, page: OcrPageImage, *, languages: tuple[str, ...]) -> OcrProviderPage: ...


class OcrRepository(Protocol):
    async def save_attempts(self, attempts: Sequence[OcrPageAttempt]) -> None: ...

    async def list_attempts(self, source_file_id: str, *, page_number: int | None = None) -> list[OcrPageAttempt]: ...

    async def list_latest(self, source_file_id: str) -> list[OcrPageAttempt]: ...

    async def list_review_queue(self) -> list[OcrPageAttempt]: ...


class OcrService:
    def __init__(
        self,
        provider: OcrProvider,
        *,
        languages: tuple[str, ...],
        review_confidence_threshold: float,
        max_concurrency: int,
    ) -> None:
        if not languages:
            raise ValueError("OCR languages are required")
        if not 0 <= review_confidence_threshold <= 1:
            raise ValueError("review_confidence_threshold must be between 0 and 1")
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self._provider = provider
        self._languages = languages
        self._review_confidence_threshold = review_confidence_threshold
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def recognize_pages(
        self,
        *,
        source_file_id: str,
        pages: tuple[OcrPageImage, ...],
        attempt_numbers: dict[int, int] | None = None,
    ) -> tuple[OcrPageAttempt, ...]:
        attempts = attempt_numbers or {}
        results = await asyncio.gather(
            *(
                self._recognize_page(
                    source_file_id=source_file_id,
                    page=page,
                    attempt_number=attempts.get(page.page_number, 1),
                )
                for page in pages
            )
        )
        return tuple(results)

    async def _recognize_page(
        self,
        *,
        source_file_id: str,
        page: OcrPageImage,
        attempt_number: int,
    ) -> OcrPageAttempt:
        base = {
            "id": f"ocr-{source_file_id}-p{page.page_number}-a{attempt_number}",
            "source_file_id": source_file_id,
            "page_number": page.page_number,
            "attempt_number": attempt_number,
            "page_image_object_key": page.object_key,
            "image_sha256": page.sha256,
            "image_width": page.width,
            "image_height": page.height,
            "provider_name": self._provider.name,
            "model_name": self._provider.model,
            "languages": self._languages,
            "created_at": datetime.now(UTC),
        }
        try:
            async with self._semaphore:
                recognized = await self._provider.recognize(page, languages=self._languages)
        except Exception as exc:
            return OcrPageAttempt(
                **base,
                status=OcrPageStatus.FAILED,
                error_code="ocr_page_failed",
                error_message=str(exc)[:500] or "OCR page failed",
            )
        status = OcrPageStatus.REVIEW_REQUIRED if recognized.mean_confidence < self._review_confidence_threshold else OcrPageStatus.COMPLETED
        return OcrPageAttempt(
            **base,
            status=status,
            raw_text=recognized.raw_text,
            mean_confidence=recognized.mean_confidence,
            rotation_degrees=recognized.rotation_degrees,
            regions=recognized.regions,
        )
