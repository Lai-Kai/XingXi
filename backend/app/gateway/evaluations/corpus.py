"""Build a tiny, explicitly synthetic corpus in a fresh evaluation database."""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime

from sqlalchemy import select
from wu_culture.releases import PublishReleaseRequest

from app.gateway.evaluations.suites import SOURCE_TEXT
from deerflow.persistence.engine import get_session_factory
from deerflow.persistence.object_storage import ObjectMetadataRow
from deerflow.persistence.wu_culture import (
    ChunkSetRow,
    CleanedOcrPageRow,
    EvidenceRow,
    OcrPageAttemptRow,
    SourceDocumentRow,
    SourceFileRow,
    SqlFullTextRepository,
    SqlKnowledgeReleaseRepository,
    TextChunkRow,
)


async def seed_corpus() -> dict:
    if os.environ.get("XINGXI_EVALUATION_CHILD") != "1":
        raise RuntimeError("Synthetic corpus seeding is restricted to a fresh evaluation child")
    sf = get_session_factory()
    now = datetime.now(UTC)
    digest = hashlib.sha256(SOURCE_TEXT.encode()).hexdigest()
    async with sf() as session:
        if (await session.execute(select(SourceDocumentRow.id).limit(1))).first():
            raise RuntimeError("Evaluation corpus requires an empty database")
        session.add(
            SourceDocumentRow(
                id="evaluation-source",
                title="测试桥志（合成测试材料）",
                edition="测试版本一",
                source_type="gazetteer",
                source_level="A",
                copyright_status="public_domain",
                authorization_status="active",
                authorization_basis="Synthetic test data",
                visibility_scope="public",
                authorized_uses_json='["internal_processing","public_quote","public_full_text"]',
                source_institution="测试",
                holder="测试",
                status="registered",
                created_by="evaluation",
                created_at=now,
            )
        )
        session.add(
            ObjectMetadataRow(
                object_key="evaluation/source.txt",
                owner_id="evaluation-source",
                kind="original",
                sha256=digest,
                mime_type="text/plain",
                size=len(SOURCE_TEXT.encode()),
                backend="local",
                storage_uri="evaluation://synthetic/source",
                original_filename="synthetic.txt",
                created_at=now,
            )
        )
        await session.flush()
        session.add(
            SourceFileRow(
                id="evaluation-file",
                document_id="evaluation-source",
                object_key="evaluation/source.txt",
                original_filename="synthetic.txt",
                mime_type="text/plain",
                size=len(SOURCE_TEXT.encode()),
                sha256=digest,
                uploaded_by="evaluation",
                uploaded_at=now,
            )
        )
        await session.flush()
        session.add(
            OcrPageAttemptRow(
                id="evaluation-ocr",
                source_file_id="evaluation-file",
                page_number=1,
                attempt_number=1,
                image_sha256=digest,
                image_width=100,
                image_height=100,
                provider_name="synthetic",
                model_name="synthetic",
                languages_json='["zh-Hans"]',
                status="completed",
                raw_text=SOURCE_TEXT,
                mean_confidence=1.0,
                rotation_degrees=0,
                created_at=now,
            )
        )
        await session.flush()
        session.add(
            CleanedOcrPageRow(
                id="evaluation-page",
                source_file_id="evaluation-file",
                ocr_attempt_id="evaluation-ocr",
                page_number=1,
                generation_number=1,
                raw_text=SOURCE_TEXT,
                raw_sha256=digest,
                clean_text=SOURCE_TEXT,
                clean_sha256=digest,
                rule_version="synthetic-v1",
                script_conversion="preserve",
                policy_json="{}",
                review_status="reviewed",
                generated_by="evaluation",
                generated_at=now,
            )
        )
        session.add(
            ChunkSetRow(
                id="evaluation-chunk-set",
                document_id="evaluation-source",
                source_file_id="evaluation-file",
                split_version="synthetic-v1",
                policy_json="{}",
                structure_json="[]",
                input_sha256=digest,
                generated_by="evaluation",
                generated_at=now,
            )
        )
        await session.flush()
        session.add(
            TextChunkRow(
                id="evaluation-chunk",
                document_id="evaluation-source",
                source_file_id="evaluation-file",
                chunk_set_id="evaluation-chunk-set",
                split_version="synthetic-v1",
                chunk_index=0,
                volume="测试卷一",
                section="桥梁",
                original_text=SOURCE_TEXT,
                normalized_text=SOURCE_TEXT,
                page_start=1,
                page_end=1,
                cleaned_page_ids_json='["evaluation-page"]',
                content_sha256=digest,
                review_status="reviewed",
            )
        )
        await session.flush()
        session.add(EvidenceRow(id="evaluation-evidence", document_id="evaluation-source", chunk_id="evaluation-chunk", quote=SOURCE_TEXT, source_level="A", review_status="reviewed"))
        await session.commit()
    repository = SqlKnowledgeReleaseRepository(sf, publication_indexer=SqlFullTextRepository(sf))
    release = await repository.publish(PublishReleaseRequest(chunk_set_ids=("evaluation-chunk-set",), expected_state_version=0, release_notes="Synthetic evaluation fixture; never product knowledge"), actor_id="evaluation", created_at=now)
    return {"release_id": release.id, "manifest_sha256": release.manifest_sha256, "dataset_sha256": digest}


async def configure_source(*, revoked: bool = False) -> None:
    sf = get_session_factory()
    async with sf() as session:
        source = await session.get(SourceDocumentRow, "evaluation-source")
        source.authorization_status = "revoked" if revoked else "active"
        await session.commit()
