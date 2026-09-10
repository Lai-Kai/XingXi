from __future__ import annotations

import asyncio

from app.gateway import app as gateway_app


def test_gateway_startup_requeues_interrupted_ingestion_jobs(monkeypatch):
    recovered = [object(), object()]

    class FakeRepository:
        def __init__(self, session_factory):
            assert session_factory == "session-factory"

        async def recover_interrupted(self, *, now, grace_seconds):
            assert now.tzinfo is not None
            assert grace_seconds == 10
            return recovered

    monkeypatch.setattr("deerflow.persistence.engine.get_session_factory", lambda: "session-factory")
    monkeypatch.setattr("deerflow.persistence.wu_culture.SqlIngestionJobRepository", FakeRepository)

    assert asyncio.run(gateway_app._recover_interrupted_ingestion_jobs(grace_seconds=10)) == 2
