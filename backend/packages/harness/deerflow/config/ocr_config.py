from typing import Literal

from pydantic import BaseModel, Field


class OcrConfig(BaseModel):
    """Scanning OCR settings backed by a configured vision model."""

    enabled: bool = Field(default=False, description="Enable OCR for scanned PDF and image source files")
    model_name: str | None = Field(default=None, description="Name of a supports_vision model from models[]")
    api_mode: Literal["chat_completions", "responses"] = Field(default="chat_completions", description="OpenAI-compatible vision request protocol")
    languages: tuple[str, ...] = Field(default=("zh-Hans", "zh-Hant"), min_length=1, description="Expected OCR languages")
    review_confidence_threshold: float = Field(default=0.8, ge=0, le=1, description="Pages below this confidence require human review")
    max_concurrency: int = Field(default=2, ge=1, le=16, description="Maximum OCR provider requests in flight")
    max_pages_per_batch: int = Field(default=50, ge=1, le=500, description="Maximum pages accepted by one OCR batch")
    timeout: float = Field(default=120.0, gt=0, le=600, description="OCR provider request timeout in seconds")
    render_dpi: int = Field(default=150, ge=72, le=300, description="PDF page rendering resolution")
