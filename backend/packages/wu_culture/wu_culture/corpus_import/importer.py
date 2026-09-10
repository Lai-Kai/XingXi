from __future__ import annotations

import hashlib
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

from wu_culture.chunking import ChunkingPolicy, ChunkSet, ChunkSourcePage, chunk_cleaned_pages
from wu_culture.cleaning import CleanedOcrPage, TextCleaningPolicy
from wu_culture.ingestion import (
    IngestionEvent,
    IngestionJob,
    IngestionStepName,
    begin_step,
    complete_step,
    create_ingestion_job,
)
from wu_culture.models import (
    AuthorizationStatus,
    AuthorizedUse,
    SourceDocument,
    SourceFile,
    SourceLevel,
    VisibilityScope,
)
from wu_culture.ocr import OcrPageAttempt, OcrPageStatus
from wu_culture.storage import ObjectKind, StoredObject

from .errors import CorpusImportError
from .models import CorpusBundleManifest, CorpusImportModel, CorpusImportPlan, CorpusQualityIssue, CorpusTextPage
from .page_parser import parse_paginated_texts
from .quality import analyze_page_quality


class CorpusImportBundle(CorpusImportModel):
    document: SourceDocument
    source_file: SourceFile
    object_metadata: StoredObject
    ocr_attempts: tuple[OcrPageAttempt, ...]
    cleaned_pages: tuple[CleanedOcrPage, ...]
    chunk_set: ChunkSet
    ingestion_job: IngestionJob
    ingestion_events: tuple[IngestionEvent, ...]
    quality_issues: tuple[CorpusQualityIssue, ...]


class CorpusImportCommitResult(CorpusImportModel):
    batch_id: str
    item_id: str
    bundle_id: str
    imported: bool


def load_bundle_pages(root: str | Path, bundle: CorpusBundleManifest) -> tuple[CorpusTextPage, ...]:
    bundle_dir = _resolve_bundle_directory(Path(root), bundle.relative_directory)
    with ExitStack() as stack:
        streams = {
            name: stack.enter_context((bundle_dir / filename).open("r", encoding="utf-8-sig", errors="strict"))
            for name, filename in {
                "raw_simplified": bundle.assets.ocr_raw_simplified,
                "raw_traditional": bundle.assets.ocr_raw_traditional,
                "clean_simplified": bundle.assets.clean_simplified,
                "clean_traditional": bundle.assets.clean_traditional,
            }.items()
        }
        return parse_paginated_texts(**streams)


def plan_import(
    root: str | Path,
    bundles: tuple[CorpusBundleManifest, ...],
    *,
    bundle_selector: str | None = None,
) -> CorpusImportPlan:
    selected = _select_bundles(bundles, bundle_selector)
    for bundle in selected:
        _verify_bundle_assets(Path(root), bundle)
    page_count = 0
    quality_issue_count = 0
    for bundle in selected:
        pages = load_bundle_pages(root, bundle)
        page_count += len(pages)
        quality_issue_count += len(analyze_page_quality(pages))
    blockers = tuple(
        sorted(
            {
                blocker
                for bundle in selected
                for blocker, missing in (
                    ("source_level_missing", bundle.source_level is None),
                    ("source_institution_missing", not bundle.source_institution),
                    ("holder_missing", not bundle.holder),
                )
                if missing
            }
        )
    )
    return CorpusImportPlan(
        bundle_count=len(selected),
        page_count=page_count,
        source_bytes=sum(sum(bundle.sizes.values()) for bundle in selected),
        quality_issue_count=quality_issue_count,
        bundle_ids=tuple(bundle.bundle_id for bundle in selected),
        blockers=blockers,
        can_commit=not blockers,
    )


def build_import_bundle(
    root: str | Path,
    bundle: CorpusBundleManifest,
    *,
    actor_id: str,
    generated_at: datetime,
    chunking_policy: ChunkingPolicy,
    allow_unconfirmed_internal: bool = False,
) -> CorpusImportBundle:
    blockers = plan_import(root, (bundle,)).blockers
    if blockers:
        if not allow_unconfirmed_internal:
            raise CorpusImportError("governance_incomplete", f"Bundle cannot be committed: {', '.join(blockers)}")
        bundle = bundle.model_copy(
            update={
                "source_level": bundle.source_level or SourceLevel.U,
                "source_institution": bundle.source_institution or "unconfirmed",
                "holder": bundle.holder or "unconfirmed",
                "authorization_status": AuthorizationStatus.ACTIVE,
                "authorization_basis": "Project owner approved internal corpus processing; public use remains unconfirmed",
                "visibility_scope": VisibilityScope.INTERNAL,
                "authorized_uses": (AuthorizedUse.INTERNAL_PROCESSING,),
            }
        )
    pages = load_bundle_pages(root, bundle)
    document_id = f"fuxianzhi-{bundle.bundle_id}"
    source_file_id = f"file-{bundle.bundle_id}"
    object_key = f"users/{document_id}/mounted/{bundle.corpus_root_id}/{bundle.relative_directory}/{bundle.assets.original_pdf}"
    pdf_sha256 = bundle.hashes[bundle.assets.original_pdf]
    pdf_size = bundle.sizes[bundle.assets.original_pdf]
    document = SourceDocument(
        id=document_id,
        title=bundle.title,
        edition=bundle.edition,
        source_type=bundle.source_type,
        source_level=bundle.source_level,
        copyright_status=bundle.copyright_status,
        source_institution=bundle.source_institution,
        holder=bundle.holder,
        authorization_status=bundle.authorization_status,
        authorization_basis=bundle.authorization_basis,
        visibility_scope=bundle.visibility_scope,
        authorized_uses=bundle.authorized_uses,
        file_hash=pdf_sha256,
        created_by=actor_id,
        created_at=generated_at,
        updated_by=actor_id,
        updated_at=generated_at,
    )
    metadata = StoredObject(
        object_key=object_key,
        owner_id=document_id,
        kind=ObjectKind.ORIGINAL,
        sha256=pdf_sha256,
        mime_type="application/pdf",
        size=pdf_size,
        backend="mounted",
        storage_uri=f"corpus://{bundle.corpus_root_id}/{bundle.relative_directory}/{bundle.assets.original_pdf}",
        original_filename=bundle.assets.original_pdf,
        created_at=generated_at,
    )
    source_file = SourceFile(
        id=source_file_id,
        document_id=document_id,
        object_key=object_key,
        original_filename=bundle.assets.original_pdf,
        mime_type="application/pdf",
        size=pdf_size,
        sha256=pdf_sha256,
        uploaded_by=actor_id,
        uploaded_at=generated_at,
    )
    policy = TextCleaningPolicy(
        rule_version="precomputed-fuxianzhi-v1",
        script_conversion="preserve",
        normalize_line_endings=False,
        join_single_line_breaks=False,
        remove_repeated_headers=False,
        remove_repeated_footers=False,
        remove_page_number_footers=False,
    )
    attempts = tuple(
        OcrPageAttempt(
            id=f"ocr-{bundle.bundle_id}-p{page.physical_page_number}-precomputed-v1",
            source_file_id=source_file_id,
            page_number=page.physical_page_number,
            attempt_number=1,
            folio_label=page.folio_label,
            provider_name="precomputed-corpus",
            model_name="unknown-precomputed-pipeline",
            languages=("zh-Hant", "zh-Hans"),
            status=OcrPageStatus.REVIEW_REQUIRED,
            raw_text=page.raw_traditional,
            mean_confidence=None,
            image_sha256=None,
            image_width=None,
            image_height=None,
            regions=(),
            created_at=generated_at,
        )
        for page in pages
    )
    cleaned_pages = tuple(
        CleanedOcrPage(
            id=f"clean-{bundle.bundle_id}-p{page.physical_page_number}-g1",
            source_file_id=source_file_id,
            ocr_attempt_id=attempt.id,
            page_number=page.physical_page_number,
            generation_number=1,
            raw_text=page.raw_traditional,
            raw_sha256=_text_sha256(page.raw_traditional),
            clean_text=page.clean_traditional,
            clean_sha256=_text_sha256(page.clean_traditional),
            rule_version=policy.rule_version,
            script_conversion=policy.script_conversion,
            policy=policy,
            changes=(),
            generated_by=actor_id,
            generated_at=generated_at,
        )
        for page, attempt in zip(pages, attempts, strict=True)
    )
    chunk_pages = tuple(
        ChunkSourcePage(
            cleaned_page_id=cleaned.id,
            page_number=page.physical_page_number,
            raw_text=page.raw_traditional,
            clean_text=page.clean_traditional,
        )
        for page, cleaned in zip(pages, cleaned_pages, strict=True)
        if page.raw_traditional and page.clean_traditional
    )
    chunk_result = chunk_cleaned_pages(
        document_id=document_id,
        source_file_id=source_file_id,
        pages=chunk_pages,
        policy=chunking_policy,
    )
    input_sha256 = _text_sha256("\x1f".join(page.clean_sha256 for page in cleaned_pages))
    chunk_set = ChunkSet(
        id=f"chunk-set-{bundle.bundle_id}-{_text_sha256(chunking_policy.model_dump_json())[:16]}",
        input_sha256=input_sha256,
        generated_by=actor_id,
        generated_at=generated_at,
        **chunk_result.model_dump(),
    )
    ingestion_job, created_event = create_ingestion_job(
        job_id=f"ingest-{bundle.bundle_id}",
        document_id=document_id,
        source_file_id=source_file_id,
        idempotency_key=f"fuxianzhi:{bundle.bundle_id}:v1",
        created_by=actor_id,
        now=generated_at,
    )
    ingestion_events = [created_event]
    output_refs = {
        IngestionStepName.PARSE: f"manifest:{bundle.bundle_id}",
        IngestionStepName.OCR: f"precomputed-pages:{len(attempts)}",
        IngestionStepName.CLEAN: f"clean-pages:{len(cleaned_pages)}",
        IngestionStepName.CHUNK: f"chunk-set:{chunk_set.id}",
    }
    for step_name in (
        IngestionStepName.PARSE,
        IngestionStepName.OCR,
        IngestionStepName.CLEAN,
        IngestionStepName.CHUNK,
    ):
        ingestion_job, event = begin_step(
            ingestion_job,
            step_name=step_name,
            worker_id="precomputed-corpus-import",
            now=generated_at,
        )
        ingestion_events.append(event)
        ingestion_job, event = complete_step(
            ingestion_job,
            step_name=step_name,
            output_ref=output_refs[step_name],
            now=generated_at,
        )
        ingestion_events.append(event)
    return CorpusImportBundle(
        document=document,
        source_file=source_file,
        object_metadata=metadata,
        ocr_attempts=attempts,
        cleaned_pages=cleaned_pages,
        chunk_set=chunk_set,
        ingestion_job=ingestion_job,
        ingestion_events=tuple(ingestion_events),
        quality_issues=analyze_page_quality(pages),
    )


def _select_bundles(bundles: tuple[CorpusBundleManifest, ...], selector: str | None) -> tuple[CorpusBundleManifest, ...]:
    if selector is None:
        return bundles
    selected = tuple(bundle for bundle in bundles if selector in {bundle.bundle_id, bundle.title, bundle.relative_directory})
    if not selected:
        raise CorpusImportError("bundle_not_found", f"No manifest bundle matches {selector!r}")
    if len(selected) > 1:
        raise CorpusImportError("bundle_ambiguous", f"More than one manifest bundle matches {selector!r}")
    return selected


def select_manifest_bundles(bundles: tuple[CorpusBundleManifest, ...], selector: str | None) -> tuple[CorpusBundleManifest, ...]:
    return _select_bundles(bundles, selector)


def _resolve_bundle_directory(root: Path, relative_directory: str) -> Path:
    root = root.resolve()
    candidate = root.joinpath(*relative_directory.split("/"))
    if candidate.is_symlink() or not candidate.is_dir():
        raise CorpusImportError("bundle_not_found", "Manifest bundle directory does not exist")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CorpusImportError("unsafe_relative_path", "Manifest bundle escapes the configured corpus root") from exc
    return resolved


def _verify_bundle_assets(root: Path, bundle: CorpusBundleManifest) -> None:
    bundle_dir = _resolve_bundle_directory(root, bundle.relative_directory)
    for filename, expected_hash in bundle.hashes.items():
        path = bundle_dir / filename
        if path.is_symlink() or not path.is_file():
            raise CorpusImportError(
                "source_asset_changed",
                "A manifest asset is missing or no longer a regular file",
                relative_path=f"{bundle.relative_directory}/{filename}",
            )
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
        stat = path.stat()
        if digest.hexdigest() != expected_hash or stat.st_size != bundle.sizes[filename]:
            raise CorpusImportError(
                "source_asset_changed",
                "A corpus asset no longer matches the reviewed manifest",
                relative_path=f"{bundle.relative_directory}/{filename}",
            )


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
