from __future__ import annotations

import json

from sqlalchemy import JSON, and_, case, cast, func, insert, or_, select, tuple_, update
from sqlalchemy.exc import IntegrityError

from deerflow.persistence.map_records import job_metadata as metadata
from deerflow.persistence.map_records import reconstruction_jobs as jobs

__all__ = ["JobStore", "metadata", "jobs"]


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

    async def list_active(self, *, after_id: str | None = None, limit: int = 100) -> list[dict]:
        """Keyset-page only live jobs; completed imports never consume the budget."""
        async with self.sessions() as session:
            if session.bind.dialect.name == "sqlite":
                status = func.json_extract(jobs.c.data_json, "$.status")
            else:
                status = cast(jobs.c.data_json, JSON)["status"].as_string()
            query = select(jobs.c.data_json).where(status.in_(["transferring", "running"]))
            if after_id is not None:
                query = query.where(jobs.c.id > after_id)
            rows = (await session.execute(query.order_by(jobs.c.id).limit(limit))).all()
            return [json.loads(row[0]) for row in rows]

    async def list_model_assets(self, bindings: dict[str, str], *, point_id: str | None = None, before: tuple[str, str] | None = None, limit: int = 100) -> list[dict]:
        """Filter completed, currently bound model candidates before keyset limiting."""
        if point_id is not None:
            bindings = {point_id: bindings[point_id]} if point_id in bindings else {}
        if not bindings:
            return []
        async with self.sessions() as session:
            if session.bind.dialect.name == "sqlite":

                def field(*path):
                    return func.json_extract(jobs.c.data_json, "$." + ".".join(path))

                def missing(*path):
                    return func.json_type(jobs.c.data_json, "$." + ".".join(path)).is_(None)

                def type_of(*path):
                    return func.json_type(jobs.c.data_json, "$." + ".".join(path))

                string_type = "text"
                size_valid = and_(type_of("artifact", "size") == "integer", field("artifact", "size") > 0)
            else:
                data = cast(jobs.c.data_json, JSON)

                def value(path):
                    item = data
                    for key in path:
                        item = item[key]
                    return item

                def field(*path):
                    return value(path).as_string()

                def missing(*path):
                    return value(path).is_(None)

                def type_of(*path):
                    return func.json_typeof(value(path))

                string_type = "string"
                # Validate numeric text without a cast: malformed historical
                # JSON must not trigger an invalid-integer SQL error.
                size_valid = and_(type_of("artifact", "size") == "number", field("artifact", "size").op("~")("^[1-9][0-9]*$"))
            # Old reconstruction records omitted entity_id. Only absence retains
            # that compatibility; explicit null and different entities are excluded.
            binding = or_(and_(missing("entity_id"), jobs.c.point_id.in_(list(bindings))), tuple_(jobs.c.point_id, field("entity_id")).in_(list(bindings.items())))
            format_ = case((missing("artifact", "format"), "ply"), else_=field("artifact", "format"))
            kind = case((missing("artifact", "kind"), "gaussian"), else_=field("artifact", "kind"))
            query = select(jobs.c.data_json).where(
                field("status") == "completed",
                type_of("artifact") == "object",
                size_valid,
                type_of("artifact", "sha256") == string_type,
                func.length(field("artifact", "sha256")) == 64,
                type_of("title") == string_type,
                func.length(field("title")) > 0,
                binding,
                format_.in_(["ply", "glb"]),
                kind.in_(["gaussian", "point_cloud", "mesh"]),
                field("id") == jobs.c.id,
                func.length(field("id")) <= 64,
                field("point_id") == jobs.c.point_id,
                field("created_at") == jobs.c.created_at,
                func.length(field("created_at")) <= 64,
            )
            if before is not None:
                created_at, job_id = before
                query = query.where(or_(jobs.c.created_at < created_at, and_(jobs.c.created_at == created_at, jobs.c.id < job_id)))
            rows = (await session.execute(query.order_by(jobs.c.created_at.desc(), jobs.c.id.desc()).limit(limit))).all()
            return [json.loads(row[0]) for row in rows]
