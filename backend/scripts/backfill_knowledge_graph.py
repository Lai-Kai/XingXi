from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

from sqlalchemy import select
from wu_culture.extraction import extract_knowledge

from deerflow.config import get_app_config
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.wu_culture import SqlKnowledgeGraphRepository
from deerflow.persistence.wu_culture.model import TextChunkRow


@dataclass(frozen=True)
class BackfillStats:
    processed: int = 0
    skipped: int = 0
    persisted: int = 0
    failed: int = 0


async def _load_batch(session_factory, last_id: str | None, batch_size: int):  # noqa: ANN001
    async with session_factory() as session:
        statement = select(
            TextChunkRow.id,
            TextChunkRow.document_id,
            TextChunkRow.source_file_id,
            TextChunkRow.normalized_text,
            TextChunkRow.original_text,
        )
        if last_id is not None:
            statement = statement.where(TextChunkRow.id > last_id)
        statement = statement.order_by(TextChunkRow.id.asc()).limit(batch_size)
        return (await session.execute(statement)).all()


async def _run(args: argparse.Namespace) -> BackfillStats:
    await init_engine_from_config(get_app_config().database)
    session_factory = get_session_factory()
    if session_factory is None:
        raise RuntimeError("knowledge graph backfill requires a SQL database")

    repository = SqlKnowledgeGraphRepository(session_factory)
    processed = 0
    skipped = 0
    persisted = 0
    failed = 0
    last_id: str | None = args.after_id
    semaphore = asyncio.Semaphore(args.workers)

    async def ingest_one(row):  # noqa: ANN001
        async with semaphore:
            text = row.normalized_text or row.original_text
            extracted = extract_knowledge(text)
            if not (extracted.entities or extracted.relations or extracted.events):
                return row, 0, None, True
            try:
                created = await repository.ingest_chunk(
                    document_id=row.document_id,
                    source_file_id=row.source_file_id or "",
                    chunk_id=row.id,
                    text=text,
                )
            except Exception as exc:  # pragma: no cover - operational guard
                return row, None, exc, False
            return row, created, None, False

    try:
        while args.limit is None or processed < args.limit:
            remaining = args.limit - processed if args.limit is not None else args.batch_size
            rows = await _load_batch(session_factory, last_id, min(args.batch_size, remaining))
            if not rows:
                break
            results = await asyncio.gather(*(ingest_one(row) for row in rows))
            retry_rows = []
            skipped_in_batch = 0
            for row, created, error, skipped_row in results:
                if skipped_row:
                    skipped_in_batch += 1
                    continue
                if error is None:
                    persisted += int(created or 0)
                else:
                    retry_rows.append((row, error))

            # Stable entity/relation IDs can briefly race when two chunks share
            # a name. Retry those rows after the parallel batch has committed.
            for row, first_error in retry_rows:
                try:
                    created = await repository.ingest_chunk(
                        document_id=row.document_id,
                        source_file_id=row.source_file_id or "",
                        chunk_id=row.id,
                        text=row.normalized_text or row.original_text,
                    )
                except Exception as exc:  # pragma: no cover - operational guard
                    failed += 1
                    print(f"[backfill] failed chunk={row.id}: {exc} (initial: {first_error})", flush=True)
                else:
                    persisted += created
            processed += len(rows)
            skipped += skipped_in_batch
            last_id = rows[-1].id
            if processed % args.progress_every == 0 or len(rows) < args.batch_size:
                print(
                    f"[backfill] processed={processed} skipped={skipped} persisted={persisted} failed={failed}",
                    flush=True,
                )
        print(
            f"[backfill] complete processed={processed} skipped={skipped} persisted={persisted} failed={failed}",
            flush=True,
        )
        return BackfillStats(processed, skipped, persisted, failed)
    finally:
        await close_engine()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill Evidence-bound graph facts from existing text chunks.")
    parser.add_argument("--batch-size", type=int, default=250, choices=range(1, 2001))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--after-id", default=None)
    parser.add_argument("--progress-every", type=int, default=100, choices=range(1, 10001))
    parser.add_argument("--workers", type=int, default=1, choices=range(1, 17))
    return parser.parse_args()


if __name__ == "__main__":
    result = asyncio.run(_run(_arguments()))
    if result.failed:
        raise SystemExit(1)
