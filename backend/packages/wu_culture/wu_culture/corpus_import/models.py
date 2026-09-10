from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from wu_culture.models import AuthorizationStatus, AuthorizedUse, CopyrightStatus, SourceLevel, SourceType, VisibilityScope


class CorpusImportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CorpusBundleAssets(CorpusImportModel):
    original_pdf: str = "book.pdf"
    ocr_raw_simplified: str = "text_raw_简体.txt"
    ocr_raw_traditional: str = "text_raw_繁体.txt"
    preview_simplified_html: str = "text_简体.html"
    clean_simplified: str = "text_简体.txt"
    preview_traditional_html: str = "text_繁体.html"
    clean_traditional: str = "text_繁体.txt"


class CorpusBundleManifest(CorpusImportModel):
    manifest_version: Literal["fuxianzhi-v1"] = "fuxianzhi-v1"
    bundle_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_root_id: str = Field(min_length=1, max_length=255)
    relative_directory: str = Field(min_length=1)
    logical_document_id: str | None = None
    region: str = Field(min_length=1)
    title: str = Field(min_length=1)
    edition: str | None = None
    part_label: str | None = None
    source_type: SourceType = SourceType.GAZETTEER
    source_level: SourceLevel | None = None
    source_institution: str | None = None
    holder: str | None = None
    copyright_status: CopyrightStatus = CopyrightStatus.UNKNOWN
    authorization_status: AuthorizationStatus = AuthorizationStatus.UNCONFIRMED
    authorization_basis: str | None = None
    visibility_scope: VisibilityScope = VisibilityScope.INTERNAL
    authorized_uses: tuple[AuthorizedUse, ...] = ()
    assets: CorpusBundleAssets = CorpusBundleAssets()
    page_count: int = Field(ge=1)
    hashes: dict[str, str]
    sizes: dict[str, int]


class CorpusScanResult(CorpusImportModel):
    corpus_root_id: str = Field(min_length=1, max_length=255)
    bundle_count: int = Field(ge=0)
    file_count: int = Field(ge=0)
    page_count: int = Field(ge=0)
    bundles: tuple[CorpusBundleManifest, ...]


class CorpusTextPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)

    physical_page_number: int = Field(ge=1)
    folio_label: str = Field(min_length=1)
    raw_simplified: str = ""
    raw_traditional: str
    clean_traditional: str
    clean_simplified: str


class CorpusQualityIssue(CorpusImportModel):
    code: Literal["raw_line_prefix_b", "missing_glyph_placeholder", "unicode_replacement_character", "empty_clean_page"]
    severity: Literal["warning"] = "warning"
    field: Literal["raw_traditional", "clean_traditional", "clean_simplified"]
    count: int = Field(ge=1)
    physical_page_number: int = Field(ge=1)
    folio_label: str = Field(min_length=1)
    message: str = Field(min_length=1)


class CorpusImportPlan(CorpusImportModel):
    bundle_count: int = Field(ge=0)
    page_count: int = Field(ge=0)
    source_bytes: int = Field(ge=0)
    quality_issue_count: int = Field(ge=0)
    bundle_ids: tuple[str, ...]
    blockers: tuple[str, ...]
    can_commit: bool
