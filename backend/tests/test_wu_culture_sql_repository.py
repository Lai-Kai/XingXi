import json
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import TypeAdapter
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture import AsyncEvidenceSearchService, EvidenceRecord, SearchRequest, SearchStatus

from deerflow.persistence.base import Base
from deerflow.persistence.wu_culture.model import WU_CULTURE_TABLES
from deerflow.persistence.wu_culture.repository import SqlEvidenceRepository

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "wu_culture" / "synthetic_evidence.json"


@pytest.fixture
def evidence_records() -> list[EvidenceRecord]:
    return TypeAdapter(list[EvidenceRecord]).validate_python(json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "wu-culture.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection: Base.metadata.create_all(sync_connection, tables=WU_CULTURE_TABLES))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_sql_repository_round_trips_evidence_after_repository_recreation(session_factory, evidence_records):
    repository = SqlEvidenceRepository(session_factory)
    await repository.add_record(evidence_records[0])

    recreated = SqlEvidenceRepository(session_factory)
    stored = await recreated.list_evidence()

    assert stored == [evidence_records[0]]


@pytest.mark.asyncio
async def test_duplicate_evidence_rolls_back_without_partial_rows(session_factory, evidence_records):
    repository = SqlEvidenceRepository(session_factory)
    await repository.add_record(evidence_records[0])

    duplicate = evidence_records[0].model_copy(update={"evidence": evidence_records[0].evidence.model_copy(update={"id": "duplicate-id"})})
    with pytest.raises(IntegrityError):
        await repository.add_record(duplicate)

    assert await repository.list_evidence() == [evidence_records[0]]


@pytest.mark.asyncio
async def test_batch_deduplicates_shared_document_and_chunk_parents(session_factory, evidence_records):
    repository = SqlEvidenceRepository(session_factory)
    first = evidence_records[0]
    second = first.model_copy(update={"evidence": first.evidence.model_copy(update={"id": "synthetic-evidence-a-2", "quote": "香溪东岸有甲桥。"})})

    await repository.add_records([first, second])

    stored = await repository.list_evidence()
    assert [record.evidence.id for record in stored] == ["synthetic-evidence-a-1", "synthetic-evidence-a-2"]


@pytest.mark.asyncio
async def test_async_search_uses_persisted_repository(session_factory, evidence_records):
    repository = SqlEvidenceRepository(session_factory)
    await repository.add_records(evidence_records)

    response = await AsyncEvidenceSearchService(repository).search(SearchRequest(query="香溪桥梁"))

    assert response.status == SearchStatus.SUPPORTED
    assert response.hits


@pytest.mark.asyncio
async def test_xingxi_search_tool_reads_persisted_database(tmp_path, evidence_records):
    from deerflow.agents.xingxi.tools import build_search_sources_tool
    from deerflow.persistence.engine import close_engine, get_session_factory, init_engine

    db_path = tmp_path / "xingxi-runtime.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        repository = SqlEvidenceRepository(session_factory)
        await repository.add_records(evidence_records)

        result = await build_search_sources_tool().ainvoke({"query": "香溪桥梁", "source_levels": ["A"], "top_k": 1})

        assert result["status"] == "supported"
        assert result["hits"][0]["citation"]["evidence_id"] == "synthetic-evidence-a-1"
    finally:
        await close_engine()
