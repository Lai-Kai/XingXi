from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wu_culture.models import EntityType, ReviewStatus, SourceLevel, SourceType


class Dynasty(StrEnum):
    PRE_QIN = "pre_qin"
    QIN = "qin"
    HAN = "han"
    THREE_KINGDOMS = "three_kingdoms"
    JIN = "jin"
    SOUTHERN_NORTHERN = "southern_northern"
    SUI = "sui"
    TANG = "tang"
    FIVE_DYNASTIES_TEN_KINGDOMS = "five_dynasties_ten_kingdoms"
    SONG = "song"
    YUAN = "yuan"
    MING = "ming"
    QING = "qing"
    REPUBLIC_OF_CHINA = "republic_of_china"
    PRC = "prc"


class StructuredSearchFilters(BaseModel):
    """Whitelisted structured filters shared by API, tools, and storage adapters."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    document_ids: tuple[str, ...] | None = Field(default=None, max_length=100)
    editions: tuple[str, ...] | None = Field(default=None, max_length=50)
    source_types: tuple[SourceType, ...] | None = Field(default=None, max_length=20)
    source_levels: tuple[SourceLevel, ...] | None = Field(default=None, max_length=6)
    dynasties: tuple[Dynasty, ...] | None = Field(default=None, max_length=20)
    entity_types: tuple[EntityType, ...] | None = Field(default=None, max_length=20)
    review_statuses: tuple[ReviewStatus, ...] | None = Field(default=None, max_length=4)
    min_spatial_confidence: float | None = Field(default=None, ge=0, le=1)
    max_spatial_confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_filters(self) -> StructuredSearchFilters:
        for name in (
            "document_ids",
            "editions",
            "source_types",
            "source_levels",
            "dynasties",
            "entity_types",
            "review_statuses",
        ):
            values = getattr(self, name)
            if values and len(values) != len(set(values)):
                raise ValueError(f"duplicate {name} filter")
        if self.document_ids and any(not value for value in self.document_ids):
            raise ValueError("document_ids cannot contain an empty value")
        if self.editions and any(not value for value in self.editions):
            raise ValueError("editions cannot contain an empty value")
        if self.min_spatial_confidence is not None and self.max_spatial_confidence is not None and self.max_spatial_confidence < self.min_spatial_confidence:
            raise ValueError("maximum spatial confidence must be greater than or equal to minimum")
        return self

    @property
    def is_empty(self) -> bool:
        return not any(value is not None for value in self.model_dump().values())
