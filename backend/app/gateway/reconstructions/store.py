from __future__ import annotations

import json

from sqlalchemy import Column, Index, Integer, MetaData, String, Table, Text, insert, select, update
from sqlalchemy.exc import IntegrityError

metadata = MetaData()
jobs = Table(
    "map_reconstruction_jobs",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(255), nullable=False),
    Column("point_id", String(255)),
    Column("request_key", String(128), nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("revision", Integer, nullable=False, default=0),
    Column("data_json", Text, nullable=False),
    Index("uq_map_reconstruction_request", "owner_id", "request_key", unique=True),
    Index("ix_map_reconstruction_point", "point_id", "created_at"),
)


class JobStore:
    def __init__(self, session_factory):
        self.sessions = session_factory

    async def get(self, job_id: str) -> dict | None:
        async with self.sessions() as session:
            raw = (await session.execute(select(jobs.c.data_json).where(jobs.c.id == job_id))).scalar_one_or_none()
            return json.loads(raw) if raw else None

    async def create(self, data: dict) -> tuple[dict, bool]:
        async with self.sessions() as session:
            try:
                await session.execute(insert(jobs).values(id=data["id"], owner_id=data["owner_id"], point_id=data.get("point_id"), request_key=data["request_id"], created_at=data["created_at"], revision=0, data_json=json.dumps(data)))
                await session.commit()
                return data, True
            except IntegrityError:
                await session.rollback()
                raw = (await session.execute(select(jobs.c.data_json).where(jobs.c.owner_id == data["owner_id"], jobs.c.request_key == data["request_id"]))).scalar_one_or_none()
                if raw is None:
                    raise
                existing = json.loads(raw)
                if existing["fingerprint"] != data["fingerprint"]:
                    raise ValueError("该上传请求已用于另一份素材，请重新选择文件后提交") from None
                return existing, False

    async def patch(self, job_id: str, changes: dict) -> dict:
        for _ in range(5):
            async with self.sessions() as session:
                row = (await session.execute(select(jobs.c.data_json, jobs.c.revision).where(jobs.c.id == job_id))).one()
                current = json.loads(row[0])
                # Late polling must never replace a terminal outcome.
                if current["status"] in {"completed", "failed", "cancelled"}:
                    return current
                value = {**current, **changes}
                result = await session.execute(update(jobs).where(jobs.c.id == job_id, jobs.c.revision == row[1]).values(data_json=json.dumps(value), revision=row[1] + 1))
                if result.rowcount:
                    await session.commit()
                    return value
                await session.rollback()
        raise RuntimeError("任务状态正在变化，请重试读取")

    async def list(self, point_id: str | None = None, *, limit: int = 100) -> list[dict]:
        query = select(jobs.c.data_json)
        if point_id is not None:
            query = query.where(jobs.c.point_id == point_id)
        async with self.sessions() as session:
            return [json.loads(row[0]) for row in (await session.execute(query.order_by(jobs.c.created_at.desc()).limit(limit))).all()]
