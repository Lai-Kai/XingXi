"""Append-only graph review history, committed with the working record's status."""

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from wu_culture.models import ReviewStatus
from wu_culture.review import ReviewConflictError
from wu_culture.review.graph import GraphReviewRecord, validate_graph_review

from .model import GraphReviewRecordRow, WuHistoricalEventRow, WuRelationRow


async def append_graph_review(
    session: AsyncSession,
    row: WuRelationRow | WuHistoricalEventRow,
    *,
    object_type: Literal["relation", "event"],
    new_status: ReviewStatus,
    reviewer_id: str,
    review_note: str | None,
    expected_status: ReviewStatus | None,
) -> None:
    previous = ReviewStatus(row.review_status)
    if expected_status is not None and previous != expected_status:
        raise ReviewConflictError("审核状态已被其他人修改，请刷新后重试。")
    note = validate_graph_review(previous, new_status, review_note)
    if not reviewer_id.strip():
        raise ValueError("审核人不能为空。")
    revision_query = select(func.coalesce(func.max(GraphReviewRecordRow.revision), 0)).where(GraphReviewRecordRow.object_type == object_type, GraphReviewRecordRow.object_id == row.id)
    revision = int((await session.execute(revision_query)).scalar_one()) + 1
    now = datetime.now(UTC)
    # Use an audit revision rather than timestamp text: legacy SQLite timestamps
    # may omit fractional seconds. The unique constraint protects the history
    # sequence if concurrent writers calculate the same next revision.
    model = type(row)
    changed = await session.execute(update(model).where(model.id == row.id, model.review_status == previous.value).values(review_status=new_status.value, updated_at=now))
    if changed.rowcount != 1:
        raise ReviewConflictError("审核状态已被其他人修改，请刷新后重试。")
    session.add(
        GraphReviewRecordRow(
            id=f"graph-review-{uuid4().hex}", object_type=object_type, object_id=row.id, revision=revision, previous_status=previous.value, new_status=new_status.value, reviewer_id=reviewer_id, review_note=note, created_at=now
        )
    )


async def list_graph_reviews(factory: async_sessionmaker, object_type: Literal["relation", "event"], object_id: str) -> list[GraphReviewRecord]:
    async with factory() as session:
        rows = (await session.execute(select(GraphReviewRecordRow).where(GraphReviewRecordRow.object_type == object_type, GraphReviewRecordRow.object_id == object_id).order_by(GraphReviewRecordRow.revision))).scalars().all()
        return [GraphReviewRecord.model_validate(row).model_copy(update={"created_at": row.created_at.replace(tzinfo=UTC) if row.created_at.tzinfo is None else row.created_at}) for row in rows]
