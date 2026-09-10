from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from wu_culture.releases import (
    KnowledgeReleaseItem,
    PublishReleaseRequest,
    build_knowledge_release,
    calculate_manifest_sha256,
)

NOW = datetime(2026, 7, 21, 15, 0, tzinfo=UTC)


def _item(chunk_id: str = "chunk-1") -> KnowledgeReleaseItem:
    return KnowledgeReleaseItem(
        ordinal=0,
        document_id="document-1",
        source_file_id="file-1",
        chunk_set_id="chunk-set-1",
        chunk_id=chunk_id,
        content_sha256="a" * 64,
        cleaned_page_ids=("cleaned-page-1",),
    )


def test_manifest_is_deterministic_and_release_is_immutable() -> None:
    item = _item()
    digest = calculate_manifest_sha256((item,))
    release = build_knowledge_release(
        release_id="release-1",
        version_number=1,
        release_notes="首个已复核版本",
        items=(item,),
        created_by="admin-1",
        created_at=NOW,
    )

    assert release.version == "v1"
    assert release.manifest_sha256 == digest
    with pytest.raises(ValidationError):
        release.version_number = 2


def test_publish_request_rejects_duplicate_chunk_sets() -> None:
    with pytest.raises(ValidationError, match="duplicate chunk set"):
        PublishReleaseRequest(
            chunk_set_ids=("chunk-set-1", "chunk-set-1"),
            release_notes="重复清单",
            expected_state_version=0,
        )


def test_manifest_changes_when_exact_content_changes() -> None:
    first = _item("chunk-1")
    second = first.model_copy(update={"content_sha256": "b" * 64})

    assert calculate_manifest_sha256((first,)) != calculate_manifest_sha256((second,))
