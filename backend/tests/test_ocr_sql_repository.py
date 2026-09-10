from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture.ocr import OcrBoundingBox, OcrPageAttempt, OcrPageStatus, OcrRegion

from deerflow.persistence.base import Base
from deerflow.persistence.wu_culture import OcrPageAttemptRow, OcrRegionRow, SqlOcrRepository


def test_ocr_repository_preserves_attempt_history_and_returns_latest_page_result(tmp_path):
    asyncio.run(_exercise_attempt_history(tmp_path))


async def _exercise_attempt_history(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ocr.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[OcrPageAttemptRow.__table__, OcrRegionRow.__table__],
            )
        )
    repository = SqlOcrRepository(async_sessionmaker(engine, expire_on_commit=False))
    created_at = datetime.now(UTC)
    failed = OcrPageAttempt(
        id="ocr-file-1-p1-a1",
        source_file_id="file-1",
        page_number=1,
        attempt_number=1,
        image_sha256="a" * 64,
        image_width=100,
        image_height=200,
        provider_name="test-ocr",
        model_name="vision-model",
        languages=("zh-Hans",),
        status=OcrPageStatus.FAILED,
        error_code="ocr_page_failed",
        error_message="temporary failure",
        created_at=created_at,
    )
    completed = OcrPageAttempt(
        id="ocr-file-1-p1-a2",
        source_file_id="file-1",
        page_number=1,
        attempt_number=2,
        image_sha256="a" * 64,
        image_width=100,
        image_height=200,
        provider_name="test-ocr",
        model_name="vision-model",
        languages=("zh-Hans",),
        status=OcrPageStatus.COMPLETED,
        raw_text="木渎",
        mean_confidence=0.95,
        regions=(OcrRegion(text="木渎", confidence=0.95, bounding_box=OcrBoundingBox(x=0.1, y=0.2, width=0.3, height=0.1)),),
        created_at=created_at + timedelta(seconds=1),
    )

    try:
        await repository.save_attempts((failed,))
        await repository.save_attempts((completed,))

        assert await repository.list_attempts("file-1", page_number=1) == [failed, completed]
        assert await repository.list_latest("file-1") == [completed]
    finally:
        await engine.dispose()


def test_review_queue_contains_only_latest_low_confidence_page_attempts(tmp_path):
    asyncio.run(_exercise_review_queue(tmp_path))


async def _exercise_review_queue(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ocr-review.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[OcrPageAttemptRow.__table__, OcrRegionRow.__table__],
            )
        )
    repository = SqlOcrRepository(async_sessionmaker(engine, expire_on_commit=False))
    created_at = datetime.now(UTC)
    base = OcrPageAttempt(
        id="ocr-file-1-p1-a1",
        source_file_id="file-1",
        page_number=1,
        attempt_number=1,
        image_sha256="a" * 64,
        image_width=100,
        image_height=200,
        provider_name="test-ocr",
        model_name="vision-model",
        languages=("zh-Hans",),
        status=OcrPageStatus.REVIEW_REQUIRED,
        raw_text="待校对",
        mean_confidence=0.6,
        regions=(OcrRegion(text="待校对", confidence=0.6, bounding_box=OcrBoundingBox(x=0.1, y=0.2, width=0.3, height=0.1)),),
        created_at=created_at,
    )
    resolved = base.model_copy(
        update={
            "id": "ocr-file-1-p1-a2",
            "attempt_number": 2,
            "status": OcrPageStatus.COMPLETED,
            "mean_confidence": 0.95,
            "created_at": created_at + timedelta(seconds=1),
        }
    )
    still_needs_review = base.model_copy(
        update={
            "id": "ocr-file-1-p2-a1",
            "page_number": 2,
            "created_at": created_at + timedelta(seconds=2),
        }
    )

    try:
        await repository.save_attempts((base, resolved, still_needs_review))

        assert await repository.list_review_queue() == [still_needs_review]
    finally:
        await engine.dispose()
