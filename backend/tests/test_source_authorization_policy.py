from datetime import UTC, datetime

import pytest
from wu_culture import (
    AsyncEvidenceSearchService,
    AuthorizationStatus,
    AuthorizedUse,
    CopyrightStatus,
    Evidence,
    EvidenceRecord,
    ReviewStatus,
    SearchRequest,
    SourceDocument,
    SourceLevel,
    SourceType,
    TextChunk,
    VisibilityScope,
    evaluate_source_access,
)


def _search_record(
    document_id: str,
    *,
    authorized: bool,
) -> EvidenceRecord:
    return EvidenceRecord(
        document=SourceDocument(
            id=document_id,
            title=f"古籍 {document_id}",
            source_type=SourceType.GAZETTEER,
            source_level=SourceLevel.A,
            copyright_status=(CopyrightStatus.AUTHORIZED if authorized else CopyrightStatus.UNKNOWN),
            authorization_status=(AuthorizationStatus.ACTIVE if authorized else AuthorizationStatus.UNCONFIRMED),
            authorization_basis="公版或书面许可" if authorized else None,
            visibility_scope=(VisibilityScope.PUBLIC if authorized else VisibilityScope.INTERNAL),
            authorized_uses=(AuthorizedUse.PUBLIC_QUOTE,) if authorized else (),
        ),
        chunk=TextChunk(
            id=f"chunk-{document_id}",
            document_id=document_id,
            original_text="木渎桥梁记载",
            normalized_text="木渎桥梁记载",
            page_start=1,
            page_end=1,
            review_status=ReviewStatus.REVIEWED,
        ),
        evidence=Evidence(
            id=f"evidence-{document_id}",
            document_id=document_id,
            chunk_id=f"chunk-{document_id}",
            quote="木渎桥梁记载",
            source_level=SourceLevel.A,
            review_status=ReviewStatus.REVIEWED,
        ),
    )


def test_unconfirmed_source_denies_public_full_text_by_default():
    document = SourceDocument(
        id="source-unconfirmed",
        title="Unconfirmed source",
        source_type=SourceType.ARCHIVE,
        source_level=SourceLevel.C,
        copyright_status=CopyrightStatus.UNKNOWN,
    )

    decision = evaluate_source_access(
        document,
        use=AuthorizedUse.PUBLIC_FULL_TEXT,
        now=datetime(2026, 7, 20, tzinfo=UTC),
    )

    assert decision.allowed is False
    assert decision.reason == "authorization_unconfirmed"


def test_expired_authorization_blocks_public_access_automatically():
    document = SourceDocument(
        id="source-expired",
        title="Expired source",
        source_type=SourceType.ARCHIVE,
        source_level=SourceLevel.B,
        copyright_status=CopyrightStatus.AUTHORIZED,
        authorization_status=AuthorizationStatus.ACTIVE,
        authorization_basis="Written permission",
        authorization_valid_until=datetime(2026, 7, 1, tzinfo=UTC),
        visibility_scope=VisibilityScope.PUBLIC,
        authorized_uses=(AuthorizedUse.PUBLIC_FULL_TEXT,),
    )

    decision = evaluate_source_access(
        document,
        use=AuthorizedUse.PUBLIC_FULL_TEXT,
        now=datetime(2026, 7, 20, tzinfo=UTC),
    )

    assert decision.allowed is False
    assert decision.reason == "authorization_expired"
    assert decision.effective_status is AuthorizationStatus.EXPIRED


@pytest.mark.parametrize(
    ("visibility", "uses", "requested_use", "status", "allowed", "reason"),
    [
        ("internal", ("internal_processing",), "internal_processing", "active", True, "authorized"),
        ("internal", ("internal_processing",), "public_quote", "active", False, "use_not_authorized"),
        ("public", ("public_quote",), "public_quote", "active", True, "authorized"),
        ("public", ("public_quote",), "public_full_text", "active", False, "use_not_authorized"),
        ("public", ("public_full_text",), "public_full_text", "revoked", False, "authorization_revoked"),
    ],
)
def test_access_policy_distinguishes_internal_quote_full_text_and_revoked(
    visibility,
    uses,
    requested_use,
    status,
    allowed,
    reason,
):
    document = SourceDocument(
        id="source-policy-matrix",
        title="Policy matrix source",
        source_type=SourceType.ARCHIVE,
        source_level=SourceLevel.B,
        copyright_status=CopyrightStatus.AUTHORIZED,
        authorization_status=AuthorizationStatus(status),
        authorization_basis="Reviewed rights basis",
        visibility_scope=VisibilityScope(visibility),
        authorized_uses=tuple(AuthorizedUse(use) for use in uses),
    )

    decision = evaluate_source_access(
        document,
        use=AuthorizedUse(requested_use),
        now=datetime(2026, 7, 20, tzinfo=UTC),
    )

    assert decision.allowed is allowed
    assert decision.reason == reason


@pytest.mark.asyncio
async def test_agent_fallback_search_excludes_sources_without_quote_permission():
    class Repository:
        async def list_evidence(self):
            return (
                _search_record("public", authorized=True),
                _search_record("internal", authorized=False),
            )

    response = await AsyncEvidenceSearchService(
        Repository(),
        authorized_use=AuthorizedUse.PUBLIC_QUOTE,
    ).search(SearchRequest(query="木渎桥梁"))

    assert [hit.citation.document_id for hit in response.hits] == ["public"]
