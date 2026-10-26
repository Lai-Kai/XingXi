from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import insert
from sqlalchemy.dialects import postgresql
from test_map_model_assets import setup as setup

from app.gateway.reconstructions.store import JobStore, jobs


def record(job_id, *, status="completed", point_id="pt-known", entity_id="entity-known", artifact=None, created_at="2026-10-25T00:00:00+00:00"):
    return {
        "id": job_id,
        "owner_id": "admin",
        "point_id": point_id,
        "entity_id": entity_id,
        "point_name": "已有古桥",
        "request_id": job_id,
        "created_at": created_at,
        "fingerprint": job_id,
        "input_type": "images",
        "quality": "balanced",
        "status": status,
        "title": job_id,
        "files": [],
        "artifact": artifact or {"size": 100, "sha256": "a" * 64, "kind": "point_cloud", "format": "ply", "point_count": 2},
    }


async def seed(store, records):
    async with store.sessions() as session:
        await session.execute(
            insert(jobs), [{"id": row["id"], "owner_id": row["owner_id"], "point_id": row["point_id"], "request_key": row["request_id"], "created_at": row["created_at"], "revision": 0, "data_json": json.dumps(row)} for row in records]
        )
        await session.commit()


@pytest.mark.asyncio
async def test_sql_model_filtering_cannot_lose_an_asset_behind_more_than_1000_non_assets(setup):
    client, service, _ = setup
    rows = [record(f"new-running-{index:04d}", status="running") for index in range(1100)]
    rows += [record("new-wrong-entity", entity_id="forged"), record("new-unknown-point", point_id="missing")]
    rows += [record("older-valid", created_at="2026-10-24T00:00:00+00:00")]
    await seed(service.store, rows)
    response = await client.get("/api/map/model-assets/page", params={"limit": 1})
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["data"]] == ["older-valid"]
    assert response.json()["next_cursor"] is None
    assert [item["id"] for item in (await client.get("/api/map/model-assets")).json()] == ["older-valid"]


@pytest.mark.asyncio
async def test_model_pages_use_stable_created_at_id_order_and_reject_cross_filter_cursors(setup):
    client, service, _ = setup
    await seed(service.store, [record("asset-a"), record("asset-c"), record("asset-b")])
    first = (await client.get("/api/map/model-assets/page", params={"limit": 2})).json()
    assert [row["id"] for row in first["data"]] == ["asset-c", "asset-b"]
    assert first["next_cursor"]
    second = (await client.get("/api/map/model-assets/page", params={"limit": 2, "cursor": first["next_cursor"]})).json()
    assert [row["id"] for row in second["data"]] == ["asset-a"]
    assert second["next_cursor"] is None
    assert (await client.get("/api/map/model-assets/page", params={"point_id": "pt-known", "cursor": first["next_cursor"]})).status_code == 400
    assert (await client.get("/api/map/model-assets/page", params={"cursor": "not-a-cursor"})).status_code == 400
    assert (await client.get("/api/map/model-assets/page", params={"limit": 0})).status_code == 422


@pytest.mark.asyncio
async def test_malformed_history_does_not_crash_or_shorten_valid_model_pages(setup):
    client, service, _ = setup
    rows = [record("asset-valid-a"), record("asset-valid-b")]
    for index, artifact in enumerate([{"size": 100}, {"size": 100, "sha256": "a" * 64, "kind": None}, {"size": 100, "sha256": "a" * 64, "kind": "mesh", "format": "obj"}, [1]]):
        rows.append(record(f"z-malformed-{index}", artifact=artifact))
    rows.append(record("z-explicit-null-entity", entity_id=None))
    rows.extend([record("z" * 65), record("z-invalid-created-at", created_at="z" * 65)])
    legacy = record("legacy-compatible")
    legacy.pop("entity_id")
    rows.append(legacy)
    await seed(service.store, rows)
    response = await client.get("/api/map/model-assets/page", params={"limit": 2, "point_id": "pt-known"})
    assert response.status_code == 200, response.text
    page = response.json()
    assert [row["id"] for row in page["data"]] == ["legacy-compatible", "asset-valid-b"]
    response = await client.get("/api/map/model-assets/page", params={"limit": 2, "point_id": "pt-known", "cursor": page["next_cursor"]})
    assert [row["id"] for row in response.json()["data"]] == ["asset-valid-a"]
    assert response.json()["next_cursor"] is None


@pytest.mark.asyncio
async def test_point_filter_cannot_return_an_asset_whose_stored_point_and_json_binding_disagree(setup):
    client, service, _ = setup
    row = record("mismatched-point", point_id="different-point")
    async with service.store.sessions() as session:
        await session.execute(insert(jobs).values(id=row["id"], owner_id=row["owner_id"], point_id="pt-known", request_key=row["request_id"], created_at=row["created_at"], revision=0, data_json=json.dumps(row)))
        await session.commit()
    rows = await service.store.list_model_assets({"pt-known": "entity-known", "different-point": "entity-known"}, point_id="pt-known")
    assert rows == []


@pytest.mark.asyncio
async def test_postgres_candidates_keep_json_missing_distinct_from_explicit_null_and_bind_keyset():
    statements = []

    class Session:
        bind = SimpleNamespace(dialect=postgresql.dialect())

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def execute(self, query):
            statements.append(str(query.compile(dialect=self.bind.dialect, compile_kwargs={"literal_binds": True})))
            return SimpleNamespace(all=lambda: [])

    store = JobStore(Session)
    assert await store.list_model_assets({"pt-known": "entity-known"}, before=("2026-10-25T00:00:00+00:00", "asset-b"), limit=2) == []
    sql = statements[0]
    # PostgreSQL -> returns SQL NULL for an absent key, JSON null for an
    # explicit null. ->> is reserved for scalar comparisons, not absence.
    assert "-> 'entity_id') IS NULL" in sql
    assert "->> 'entity_id') AS VARCHAR" in sql
    assert "json_typeof" in sql and " = 'object'" in sql
    assert "ORDER BY map_reconstruction_jobs.created_at DESC, map_reconstruction_jobs.id DESC" in sql
    assert "map_reconstruction_jobs.id < 'asset-b'" in sql and "LIMIT 2" in sql
