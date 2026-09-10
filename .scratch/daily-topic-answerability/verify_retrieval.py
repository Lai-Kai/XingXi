"""Read-only replay of the reported topic through Gateway context and tools."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture import EvidenceSearchService, InMemoryEvidenceRepository

from app.gateway.services import inject_knowledge_release_context, merge_run_context_overrides, resolve_active_knowledge_release_metadata
from deerflow.agents.xingxi.tools import build_search_sources_tool
from deerflow.persistence.wu_culture import SqlEvidenceRepository, SqlFullTextRepository, SqlKnowledgeReleaseRepository


async def main():
    # Periodic polling compensates for the restricted runner losing SQLite
    # worker-thread socket wakeups. It does not replace database operations.
    loop = asyncio.get_running_loop()

    def tick():
        loop.call_later(0.01, tick)

    tick()
    database = Path(__file__).resolve().parents[2] / "backend/.deer-flow/data/deerflow.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///file:{database}?mode=ro&uri=true")
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        metadata = await resolve_active_knowledge_release_metadata(SqlKnowledgeReleaseRepository(factory))
        evidence_id = "fulltext-release-2c7aafe43b4247fa86ab0d6b951590e7-chunk-0625e762d386f7873718b935a571c03aca0b4eabf76b91d1e3fd018c569796b9"
        tool = build_search_sources_tool(
            search_service=EvidenceSearchService(InMemoryEvidenceRepository()),
            fulltext_repository=SqlFullTextRepository(factory),
            daily_topic_evidence_repository=SqlEvidenceRepository(factory),
        )
        for mode in ("daily_topic", "ordinary_question"):
            config = {}
            if mode == "daily_topic":
                merge_run_context_overrides(
                    config,
                    {
                        "daily_topic_query": "陆玩 灵岩山",
                        "daily_topic_document_ids": ["fuxianzhi-14c3406ddba068ef1758e22a9dc22c4fd91bf7fb4d106fd2d4484b3109932267"],
                        "daily_topic_evidence_ids": [evidence_id],
                    },
                )
            inject_knowledge_release_context(config, metadata)
            result = await tool.coroutine(
                query="陆玩 灵岩寺 历史联系",
                runtime=SimpleNamespace(context=config["context"], config=config),
            )
            items = result["evidence_pack"]["items"]
            assert any(item["evidence_id"] == evidence_id for item in items), result
            assert result["evidence_pack"]["release_id"] == metadata["knowledge_release_id"]
            print(
                json.dumps(
                    {
                        "mode": mode,
                        "status": result["status"],
                        "resolved_query": result.get("resolved_query"),
                        "attached": result.get("attached_daily_topic_evidence", False),
                        "attempts": result.get("retrieval_attempts"),
                        "items": [
                            {key: item.get(key) for key in ("evidence_id", "document_title", "page_start", "page_end", "source_level", "review_status")}
                            for item in items
                        ],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    finally:
        await engine.dispose()


asyncio.run(main())
