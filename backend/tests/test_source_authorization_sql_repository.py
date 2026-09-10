from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture import (
    AuthorizationStatus,
    AuthorizedUse,
    CopyrightStatus,
    SourceAuthorizationEvent,
    SourceDocument,
    SourceLevel,
    SourceType,
    VisibilityScope,
)

from deerflow.persistence.base import Base
from deerflow.persistence.wu_culture import (
    SourceAuthorizationEventRow,
    SourceDocumentRow,
    SqlSourceDocumentRepository,
)


def test_authorization_update_and_audit_survive_repository_recreation(tmp_path):
    asyncio.run(_exercise_authorization_persistence(tmp_path))


async def _exercise_authorization_persistence(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'authorization.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[SourceDocumentRow.__table__, SourceAuthorizationEventRow.__table__],
            )
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    document = SourceDocument(
        id="source-authorization",
        title="Authorized source",
        source_type=SourceType.ARCHIVE,
        source_level=SourceLevel.B,
        copyright_status=CopyrightStatus.UNKNOWN,
    )
    repository = SqlSourceDocumentRepository(session_factory)
    try:
        await repository.create(document)
        updated = document.model_copy(
            update={
                "copyright_status": CopyrightStatus.AUTHORIZED,
                "authorization_status": AuthorizationStatus.ACTIVE,
                "authorization_basis": "Written permission",
                "visibility_scope": VisibilityScope.PUBLIC,
                "authorized_uses": (AuthorizedUse.PUBLIC_QUOTE,),
                "updated_by": "admin-1",
                "updated_at": now,
            }
        )
        event = SourceAuthorizationEvent(
            id="authorization-event-1",
            document_id=document.id,
            previous_status=AuthorizationStatus.UNCONFIRMED,
            new_status=AuthorizationStatus.ACTIVE,
            previous_copyright_status=CopyrightStatus.UNKNOWN,
            new_copyright_status=CopyrightStatus.AUTHORIZED,
            new_visibility_scope=VisibilityScope.PUBLIC,
            new_authorized_uses=(AuthorizedUse.PUBLIC_QUOTE,),
            changed_by="admin-1",
            changed_at=now,
            reason="Initial review",
        )

        await repository.update_authorization(updated, event)

        recreated = SqlSourceDocumentRepository(session_factory)
        assert await recreated.get(document.id) == updated
        assert await recreated.list_authorization_events(document.id) == [event]
    finally:
        await engine.dispose()
