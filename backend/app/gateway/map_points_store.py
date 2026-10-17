"""Persistent user-selected map locations, separate from published knowledge."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Column, Float, Index, MetaData, String, Table, insert, select
from sqlalchemy.exc import IntegrityError

metadata = MetaData()
points = Table(
    "map_custom_points",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(255), nullable=False),
    Column("request_key", String(128), nullable=False),
    Column("name", String(120), nullable=False),
    Column("lon", Float, nullable=False),
    Column("lat", Float, nullable=False),
    Column("created_at", String(64), nullable=False),
    Index("uq_map_custom_point_request", "owner_id", "request_key", unique=True),
)


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
