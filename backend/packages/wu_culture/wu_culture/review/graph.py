"""Review transitions for working graph records, independent of published Releases."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from wu_culture.models import ReviewStatus


class GraphReviewRecord(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: str
    object_type: Literal["relation", "event"]
    object_id: str
    revision: int
    previous_status: ReviewStatus
    new_status: ReviewStatus
    reviewer_id: str
    review_note: str | None = None
    created_at: datetime


def validate_graph_review(previous: ReviewStatus, new: ReviewStatus, note: str | None) -> str | None:
    if previous == new:
        raise ValueError("审核状态未改变，请选择其他结果。")
    note = note.strip() if note else None
    if (previous != ReviewStatus.PENDING or new in (ReviewStatus.REJECTED, ReviewStatus.DISPUTED)) and not note:
        raise ValueError("驳回、有争议或修改已有审核结论时必须填写审核备注。")
    if note and len(note) > 2000:
        raise ValueError("审核备注不能超过 2000 字。")
    return note or None
