from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from wu_culture import ReviewStatus
from wu_culture.review import (
    ReviewBatchRequest,
    ReviewRequest,
    ReviewTargetType,
    build_review_record,
    evaluate_publication_gate,
)

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


def test_review_records_are_append_only_revisions_with_previous_status():
    request = ReviewRequest(
        target_type=ReviewTargetType.CHUNK,
        target_id="chunk-1",
        decision=ReviewStatus.REVIEWED,
        comment="原文、清洗文本与页码一致",
    )

    first = build_review_record(
        record_id="review-1",
        document_id="document-1",
        source_file_id="file-1",
        request=request,
        previous_status=ReviewStatus.PENDING,
        revision=1,
        reviewed_by="admin-1",
        reviewed_at=NOW,
    )
    second = build_review_record(
        record_id="review-2",
        document_id="document-1",
        source_file_id="file-1",
        request=request.model_copy(update={"decision": ReviewStatus.DISPUTED, "comment": "版本异文待确认"}),
        previous_status=first.decision,
        revision=2,
        reviewed_by="admin-2",
        reviewed_at=NOW,
    )

    assert first.previous_status is ReviewStatus.PENDING
    assert first.decision is ReviewStatus.REVIEWED
    assert second.previous_status is ReviewStatus.REVIEWED
    assert second.decision is ReviewStatus.DISPUTED
    assert second.revision == 2
    assert first.id != second.id


@pytest.mark.parametrize("decision", [ReviewStatus.REJECTED, ReviewStatus.DISPUTED])
def test_return_and_dispute_require_an_operator_comment(decision):
    with pytest.raises(ValidationError, match="comment is required"):
        ReviewRequest(
            target_type=ReviewTargetType.PAGE,
            target_id="clean-page-1",
            decision=decision,
        )


def test_pending_is_not_a_review_decision():
    with pytest.raises(ValidationError, match="pending is not a review decision"):
        ReviewRequest(
            target_type=ReviewTargetType.CHUNK,
            target_id="chunk-1",
            decision=ReviewStatus.PENDING,
        )


def test_batch_rejects_duplicate_targets_before_any_database_write():
    item = ReviewRequest(
        target_type=ReviewTargetType.CHUNK,
        target_id="chunk-1",
        decision=ReviewStatus.REVIEWED,
    )

    with pytest.raises(ValidationError, match="duplicate review target"):
        ReviewBatchRequest(items=(item, item))


def test_publication_gate_requires_reviewed_chunk_and_every_clean_page():
    blocked_chunk = evaluate_publication_gate(
        chunk_status=ReviewStatus.DISPUTED,
        page_statuses=(ReviewStatus.REVIEWED,),
    )
    blocked_page = evaluate_publication_gate(
        chunk_status=ReviewStatus.REVIEWED,
        page_statuses=(ReviewStatus.REVIEWED, ReviewStatus.REJECTED),
    )
    allowed = evaluate_publication_gate(
        chunk_status=ReviewStatus.REVIEWED,
        page_statuses=(ReviewStatus.REVIEWED, ReviewStatus.REVIEWED),
    )

    assert blocked_chunk.allowed is False
    assert blocked_chunk.reasons == ("chunk_not_reviewed",)
    assert blocked_page.allowed is False
    assert blocked_page.reasons == ("page_not_reviewed",)
    assert allowed.allowed is True
    assert allowed.reasons == ()
