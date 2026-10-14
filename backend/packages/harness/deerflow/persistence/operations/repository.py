from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    return json.loads(value)


class OperationsRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        publication_map_manifest: dict[str, Any] | None = None,
        publication_map_manifest_factory: Callable[[Any], Awaitable[dict[str, Any]]] | None = None,
    ) -> None:
        self._sf = session_factory
        self._publication_map_manifest = publication_map_manifest
        self._publication_map_manifest_factory = publication_map_manifest_factory

    async def record_event(self, body, *, user_id: str) -> dict[str, Any]:
        event_id = str(uuid.uuid4())
        occurred_at = datetime.now(UTC)
        values = body.model_dump()
        async with self._sf() as session:
            if body.event_key:
                existing = (
                    (
                        await session.execute(
                            text("SELECT * FROM wu_operation_events WHERE event_key=:event_key"),
                            {"event_key": body.event_key},
                        )
                    )
                    .mappings()
                    .first()
                )
                if existing:
                    return {
                        "id": existing["id"],
                        **body.model_dump(),
                        "metadata": _loads(existing["metadata_json"], {}),
                        "user_id": existing["user_id"],
                        "occurred_at": existing["occurred_at"],
                    }
            await session.execute(
                text("""
                INSERT INTO wu_operation_events
                (id,event_type,event_key,user_id,thread_id,run_id,release_id,entity_id,entity_name,citation_count,is_accurate,refused,refusal_compliant,metadata_json,occurred_at)
                VALUES (:id,:event_type,:event_key,:user_id,:thread_id,:run_id,:release_id,:entity_id,:entity_name,:citation_count,:is_accurate,:refused,:refusal_compliant,:metadata_json,:occurred_at)
            """),
                {**values, "id": event_id, "user_id": user_id, "metadata_json": _json(values.pop("metadata", {})), "occurred_at": occurred_at},
            )
            await session.commit()
        return {"id": event_id, **body.model_dump(), "user_id": user_id, "occurred_at": occurred_at}

    async def dashboard(self, *, days: int):
        from app.gateway.routers.operations import build_dashboard_metrics

        since = datetime.now(UTC) - timedelta(days=days)
        async with self._sf() as session:
            answer_rows = (await session.execute(text("SELECT citation_count,is_accurate,refused,refusal_compliant FROM wu_operation_events WHERE event_type='answer_completed' AND occurred_at>=:since"), {"since": since})).mappings().all()
            unanswered = (await session.execute(text("SELECT COUNT(*) FROM wu_operation_events WHERE event_type='search_miss' AND occurred_at>=:since"), {"since": since})).scalar_one()
            map_clicks = (await session.execute(text("SELECT COUNT(*) FROM wu_operation_events WHERE event_type='map_point_click' AND occurred_at>=:since"), {"since": since})).scalar_one()
            corrections = (await session.execute(text("SELECT COUNT(*) FROM wu_correction_records WHERE created_at>=:since"), {"since": since})).scalar_one()
            hot_rows = (
                await session.execute(
                    text("SELECT entity_id,MAX(entity_name) AS entity_name,COUNT(*) AS views FROM wu_operation_events WHERE entity_id IS NOT NULL AND occurred_at>=:since GROUP BY entity_id ORDER BY views DESC LIMIT 10"), {"since": since}
                )
            ).all()
            ratings = list((await session.execute(text("SELECT rating FROM feedback WHERE created_at>=:since"), {"since": since})).scalars().all())
            evaluation_outcomes = [
                bool(value)
                for value in (
                    await session.execute(
                        text("""SELECT result.passed FROM wu_evaluation_results AS result
                        JOIN wu_evaluation_runs AS run ON run.id=result.run_id
                        WHERE run.created_at>=:since"""),
                        {"since": since},
                    )
                )
                .scalars()
                .all()
            ]
        return build_dashboard_metrics(
            answer_events=[dict(row) for row in answer_rows],
            feedback_ratings=ratings,
            unanswered_count=unanswered,
            map_click_count=map_clicks,
            correction_count=corrections,
            hot_entities=[(row[0], row[1] or row[0], row[2]) for row in hot_rows],
            evaluation_outcomes=evaluation_outcomes,
        )

    async def create_correction(self, body, *, actor_id: str) -> dict[str, Any]:
        record_id = str(uuid.uuid4())
        created_at = datetime.now(UTC)
        values = body.model_dump()
        async with self._sf() as session:
            await session.execute(
                text(
                    """INSERT INTO wu_correction_records
                    (id,target_type,target_id,release_id,summary,before_json,after_json,actor_id,created_at)
                    VALUES (:id,:target_type,:target_id,:release_id,:summary,:before_json,:after_json,:actor_id,:created_at)"""
                ),
                {**values, "id": record_id, "before_json": _json(values.pop("before")), "after_json": _json(values.pop("after")), "actor_id": actor_id, "created_at": created_at},
            )
            await session.commit()
        return {"id": record_id, **body.model_dump(), "actor_id": actor_id, "created_at": created_at}

    async def list_corrections(self, *, limit: int) -> list[dict[str, Any]]:
        async with self._sf() as session:
            rows = (await session.execute(text("SELECT * FROM wu_correction_records ORDER BY created_at DESC LIMIT :limit"), {"limit": limit})).mappings().all()
        return [
            {
                "id": row["id"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "release_id": row["release_id"],
                "summary": row["summary"],
                "before": _loads(row["before_json"], {}),
                "after": _loads(row["after_json"], {}),
                "actor_id": row["actor_id"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    async def create_evaluation_case(self, body, *, actor_id: str) -> dict[str, Any]:
        case_id = str(uuid.uuid4())
        created_at = datetime.now(UTC)
        values = body.model_dump()
        async with self._sf() as session:
            await session.execute(
                text(
                    """INSERT INTO wu_evaluation_cases
                    (id,name,question,expected_status,min_citations,required_terms_json,active,created_by,created_at)
                    VALUES (:id,:name,:question,:expected_status,:min_citations,:required_terms_json,:active,:created_by,:created_at)"""
                ),
                {**values, "id": case_id, "required_terms_json": _json(values.pop("required_terms")), "created_by": actor_id, "created_at": created_at},
            )
            await session.commit()
        return {"id": case_id, **body.model_dump(), "created_by": actor_id, "created_at": created_at}

    async def list_evaluation_cases(self) -> list[dict[str, Any]]:
        async with self._sf() as session:
            rows = (await session.execute(text("SELECT * FROM wu_evaluation_cases ORDER BY created_at DESC"))).mappings().all()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "question": row["question"],
                "expected_status": row["expected_status"],
                "min_citations": row["min_citations"],
                "required_terms": _loads(row["required_terms_json"], []),
                "active": bool(row["active"]),
                "created_by": row["created_by"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    async def create_evaluation_run(self, body, *, actor_id: str) -> dict[str, Any]:
        from deerflow.persistence.operations.grading import grade_manual_regression

        cases = await self.list_evaluation_cases()
        selected = [case for case in cases if case["active"] and (not body.case_ids or case["id"] in body.case_ids)]
        if not selected or (body.case_ids and set(body.case_ids) != {case["id"] for case in selected}):
            raise ValueError("Select at least one existing active evaluation case")
        report = grade_manual_regression(cases=selected, observations=[item.model_dump() for item in body.observations])
        run_id = str(uuid.uuid4())
        created_at = datetime.now(UTC)
        async with self._sf() as session:
            await session.execute(
                text(
                    """INSERT INTO wu_evaluation_runs
                    (id,release_id,asset_version_id,status,total,passed,pass_rate,created_by,created_at)
                    VALUES (:id,:release_id,:asset_version_id,'completed',:total,:passed,:pass_rate,:created_by,:created_at)"""
                ),
                {
                    "id": run_id,
                    "release_id": body.release_id,
                    "asset_version_id": body.asset_version_id,
                    "total": report["total"],
                    "passed": report["passed"],
                    "pass_rate": report["pass_rate"],
                    "created_by": actor_id,
                    "created_at": created_at,
                },
            )
            for result in report["results"]:
                await session.execute(
                    text(
                        """INSERT INTO wu_evaluation_results
                        (id,run_id,case_id,actual_status,citation_count,answer,passed,failure_reasons_json)
                        VALUES (:id,:run_id,:case_id,:actual_status,:citation_count,:answer,:passed,:failure_reasons_json)"""
                    ),
                    {"id": str(uuid.uuid4()), "run_id": run_id, **{key: value for key, value in result.items() if key != "failure_reasons"}, "failure_reasons_json": _json(result["failure_reasons"])},
                )
            await session.commit()
        return {
            "id": run_id,
            "release_id": body.release_id,
            "asset_version_id": body.asset_version_id,
            "status": "completed",
            "total": report["total"],
            "passed": report["passed"],
            "pass_rate": report["pass_rate"],
            "created_by": actor_id,
            "created_at": created_at,
            "results": report["results"],
        }

    async def list_evaluation_runs(self, *, limit: int) -> list[dict[str, Any]]:
        async with self._sf() as session:
            runs = (
                (
                    await session.execute(
                        text("SELECT id,release_id,asset_version_id,status,total,passed,pass_rate,created_by,created_at FROM wu_evaluation_runs WHERE execution_mode='manual' ORDER BY created_at DESC LIMIT :limit"), {"limit": limit}
                    )
                )
                .mappings()
                .all()
            )
            output = []
            for run in runs:
                results = (await session.execute(text("SELECT * FROM wu_evaluation_results WHERE run_id=:run_id ORDER BY id"), {"run_id": run["id"]})).mappings().all()
                output.append(
                    {
                        **dict(run),
                        "results": [
                            {
                                "case_id": row["case_id"],
                                "actual_status": row["actual_status"],
                                "citation_count": row["citation_count"],
                                "answer": row["answer"],
                                "passed": bool(row["passed"]),
                                "failure_reasons": _loads(row["failure_reasons_json"], []),
                            }
                            for row in results
                        ],
                    }
                )
        return output

    async def ensure_asset_snapshot(self, *, release_id: str, release_version: str, map_manifest: dict[str, Any], actor_id: str) -> dict[str, Any]:
        async with self._sf() as session:
            snapshot = await self.ensure_asset_snapshot_in_session(
                session,
                release_id=release_id,
                release_version=release_version,
                map_manifest=map_manifest,
                actor_id=actor_id,
                created_at=datetime.now(UTC),
            )
            await session.commit()
        return snapshot

    async def prepare_release(self, session, release, *, actor_id: str, created_at) -> dict[str, Any]:  # noqa: ANN001
        if self._publication_map_manifest_factory is not None:
            map_manifest = await self._publication_map_manifest_factory(release)
        elif self._publication_map_manifest is not None:
            # Compatibility for callers using the pre-0038 constructor. New
            # release publication uses the release-scoped factory above.
            map_manifest = self._publication_map_manifest
        else:
            raise RuntimeError("release asset preparation requires a versioned map manifest")
        return await self.ensure_asset_snapshot_in_session(
            session,
            release_id=release.id,
            release_version=release.version,
            map_manifest=map_manifest,
            actor_id=actor_id,
            created_at=created_at,
        )

    @staticmethod
    async def ensure_release_ready(session: AsyncSession, release) -> None:  # noqa: ANN001
        row = (
            (
                await session.execute(
                    text("SELECT * FROM wu_asset_versions WHERE knowledge_release_id=:release_id"),
                    {"release_id": release.id},
                )
            )
            .mappings()
            .first()
        )
        if row is None or not row["graph_manifest_sha256"] or not row["map_manifest_sha256"]:
            raise RuntimeError(f"knowledge release {release.id!r} does not have complete graph and map assets")
        # Pre-0038 databases have no map body at all. They can still be read
        # by old isolated callers, but an upgraded schema must not activate a
        # release whose map snapshot is missing.
        if "map_manifest_json" in row and not row["map_manifest_json"]:
            raise RuntimeError(f"knowledge release {release.id!r} does not have a persisted map snapshot")

    @staticmethod
    async def ensure_asset_snapshot_in_session(
        session: AsyncSession,
        *,
        release_id: str,
        release_version: str,
        map_manifest: dict[str, Any],
        actor_id: str,
        created_at,
    ) -> dict[str, Any]:
        existing = (
            (
                await session.execute(
                    text("SELECT * FROM wu_asset_versions WHERE knowledge_release_id=:release_id"),
                    {"release_id": release_id},
                )
            )
            .mappings()
            .first()
        )
        if existing:
            if "map_manifest_json" not in existing or existing["map_manifest_json"]:
                return dict(existing)
            map_json = _json(map_manifest)
            await session.execute(
                text("UPDATE wu_asset_versions SET map_manifest_sha256=:map_manifest_sha256, map_manifest_json=:map_manifest_json, map_point_count=:map_point_count WHERE knowledge_release_id=:release_id"),
                {
                    "release_id": release_id,
                    "map_manifest_sha256": hashlib.sha256(map_json.encode()).hexdigest(),
                    "map_manifest_json": map_json,
                    "map_point_count": len(map_manifest.get("points", [])),
                },
            )
            refreshed = (
                (
                    await session.execute(
                        text("SELECT * FROM wu_asset_versions WHERE knowledge_release_id=:release_id"),
                        {"release_id": release_id},
                    )
                )
                .mappings()
                .first()
            )
            if refreshed is None:
                raise RuntimeError(f"asset snapshot disappeared for release {release_id!r}")
            return dict(refreshed)
        entities = (
            (
                await session.execute(
                    text("SELECT id,canonical_name,entity_type,review_status FROM wu_entities WHERE release_id=:release_id ORDER BY id"),
                    {"release_id": release_id},
                )
            )
            .mappings()
            .all()
        )
        graph_hash = hashlib.sha256(_json([dict(row) for row in entities]).encode()).hexdigest()
        map_hash = hashlib.sha256(_json(map_manifest).encode()).hexdigest()
        snapshot = {
            "id": str(uuid.uuid4()),
            "knowledge_release_id": release_id,
            "knowledge_release_version": release_version,
            "graph_manifest_sha256": graph_hash,
            "map_manifest_sha256": map_hash,
            "map_manifest_json": _json(map_manifest),
            "entity_count": len(entities),
            "map_point_count": len(map_manifest.get("points", [])),
            "created_by": actor_id,
            "created_at": created_at,
        }
        columns = (await session.execute(text("SELECT * FROM wu_asset_versions LIMIT 0"))).keys()
        if "map_manifest_json" in columns:
            await session.execute(
                text(
                    """INSERT INTO wu_asset_versions
                    (id,knowledge_release_id,knowledge_release_version,graph_manifest_sha256,map_manifest_sha256,
                     map_manifest_json,entity_count,map_point_count,created_by,created_at)
                    VALUES (:id,:knowledge_release_id,:knowledge_release_version,:graph_manifest_sha256,:map_manifest_sha256,
                            :map_manifest_json,:entity_count,:map_point_count,:created_by,:created_at)"""
                ),
                snapshot,
            )
        else:
            # Compatibility for isolated callers still using a pre-0038
            # schema. Gateway startup upgrades production databases first.
            await session.execute(
                text(
                    """INSERT INTO wu_asset_versions
                    (id,knowledge_release_id,knowledge_release_version,graph_manifest_sha256,map_manifest_sha256,
                     entity_count,map_point_count,created_by,created_at)
                    VALUES (:id,:knowledge_release_id,:knowledge_release_version,:graph_manifest_sha256,:map_manifest_sha256,
                            :entity_count,:map_point_count,:created_by,:created_at)"""
                ),
                snapshot,
            )
        await session.flush()
        return snapshot

    async def list_asset_versions(self) -> list[dict[str, Any]]:
        async with self._sf() as session:
            rows = (
                (
                    await session.execute(
                        text("SELECT id,knowledge_release_id,knowledge_release_version,graph_manifest_sha256,map_manifest_sha256,entity_count,map_point_count,created_by,created_at FROM wu_asset_versions ORDER BY created_at DESC")
                    )
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]
