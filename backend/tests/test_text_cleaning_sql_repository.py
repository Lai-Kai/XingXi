from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture.cleaning import CleanedOcrPage, RawOcrPage, TextCleaningPolicy, clean_ocr_page

from deerflow.persistence.base import Base
from deerflow.persistence.wu_culture import CleanedOcrPageRow, SqlTextCleaningRepository, TextCleaningChangeRow


def test_cleaning_repository_preserves_generations_and_returns_latest(tmp_path):
    asyncio.run(_exercise_cleaning_generations(tmp_path))


async def _exercise_cleaning_generations(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cleaning.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[CleanedOcrPageRow.__table__, TextCleaningChangeRow.__table__],
            )
        )
    repository = SqlTextCleaningRepository(async_sessionmaker(engine, expire_on_commit=False))
    raw = RawOcrPage(source_file_id="file-1", ocr_attempt_id="ocr-file-1-p1-a1", page_number=1, raw_text="後臺\n史料")
    first_policy = TextCleaningPolicy(rule_version="clean-v1", script_conversion="preserve")
    second_policy = TextCleaningPolicy(rule_version="clean-v2", script_conversion="simplified")
    now = datetime.now(UTC)
    first = CleanedOcrPage(
        id="clean-file-1-p1-g1",
        generation_number=1,
        policy=first_policy,
        generated_by="admin-1",
        generated_at=now,
        **clean_ocr_page(raw, policy=first_policy).model_dump(),
    )
    second = CleanedOcrPage(
        id="clean-file-1-p1-g2",
        generation_number=2,
        policy=second_policy,
        generated_by="admin-1",
        generated_at=now + timedelta(seconds=1),
        **clean_ocr_page(raw, policy=second_policy).model_dump(),
    )

    try:
        await repository.save(first)
        await repository.save(second)

        assert await repository.list_generations(raw.ocr_attempt_id) == [first, second]
        assert await repository.list_latest(raw.source_file_id) == [second]
        assert first.raw_sha256 == second.raw_sha256
    finally:
        await engine.dispose()
