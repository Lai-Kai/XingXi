from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.wu_culture.knowledge_seed import apply_knowledge_seed, load_knowledge_seed


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load Evidence-bound府县志 knowledge drafts into the active release.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "fuxianzhi_knowledge_seed.json",
    )
    parser.add_argument("--release-id", help="Override the active Release ID after validation.")
    parser.add_argument("--database-url", help="Use an explicit SQLAlchemy async database URL.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    engine = None
    if args.database_url:
        engine = create_async_engine(args.database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
    else:
        from deerflow.config import get_app_config

        await init_engine_from_config(get_app_config().database)
        session_factory = get_session_factory()
        if session_factory is None:
            raise RuntimeError("knowledge seed requires a SQL database")
    try:
        report = await apply_knowledge_seed(
            session_factory,
            load_knowledge_seed(args.manifest),
            release_id=args.release_id,
            dry_run=args.dry_run,
        )
        print(report.model_dump_json(indent=2))
    finally:
        if engine is not None:
            await engine.dispose()
        else:
            await close_engine()


if __name__ == "__main__":
    asyncio.run(_run(_arguments()))
