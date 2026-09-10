from __future__ import annotations

from datetime import UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from wu_culture.storage import ObjectKind, StoredObject

from .model import ObjectMetadataRow


class SqlObjectMetadataRepository:
    """Stores object metadata only; object bytes remain in the configured backend."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, metadata: StoredObject) -> None:
        async with self._session_factory() as session:
            existing = await session.get(ObjectMetadataRow, metadata.object_key)
            if existing is not None:
                if self._to_domain(existing) != metadata:
                    raise ValueError(f"Conflicting metadata for object_key {metadata.object_key!r}")
                return
            session.add(self._to_row(metadata))
            await session.commit()

    async def get(self, *, owner_id: str, object_key: str) -> StoredObject | None:
        statement = select(ObjectMetadataRow).where(
            ObjectMetadataRow.object_key == object_key,
            ObjectMetadataRow.owner_id == owner_id,
        )
        async with self._session_factory() as session:
            row = (await session.execute(statement)).scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

    @staticmethod
    def _to_row(metadata: StoredObject) -> ObjectMetadataRow:
        return ObjectMetadataRow(**metadata.model_dump(mode="python"))

    @staticmethod
    def _to_domain(row: ObjectMetadataRow) -> StoredObject:
        created_at = row.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return StoredObject(
            object_key=row.object_key,
            owner_id=row.owner_id,
            kind=ObjectKind(row.kind),
            sha256=row.sha256,
            mime_type=row.mime_type,
            size=row.size,
            backend=row.backend,
            storage_uri=row.storage_uri,
            original_filename=row.original_filename,
            created_at=created_at,
        )
