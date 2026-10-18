"""Persistent user-selected map locations, separate from published knowledge."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from deerflow.persistence.map_records import custom_points as points
from deerflow.persistence.map_records import point_metadata as metadata

__all__ = ["MapPointsStore", "metadata", "points"]


class MapPointsStore:
    def __init__(self, sessions):
        self.sessions = sessions

    async def list(self):
        async with self.sessions() as session:
            rows = await session.execute(select(points).order_by(points.c.created_at, points.c.id))
            return [dict(row) for row in rows.mappings()]

    async def create(self, *, owner_id: str, request_id: str, name: str, lon: float, lat: float):
        data = {"id": str(uuid4()), "owner_id": owner_id, "request_key": request_id, "name": name, "lon": lon, "lat": lat, "created_at": datetime.now(UTC).isoformat()}
        async with self.sessions() as session:
            try:
                await session.execute(insert(points).values(**data))
                await session.commit()
                return data
            except IntegrityError:
                await session.rollback()
                row = (await session.execute(select(points).where(points.c.owner_id == owner_id, points.c.request_key == request_id))).mappings().one_or_none()
                if row is None:
                    raise
                if any(row[key] != data[key] for key in ("name", "lon", "lat")):
                    raise ValueError("该请求已创建其他点位，请重新选点后保存") from None
                return dict(row)
