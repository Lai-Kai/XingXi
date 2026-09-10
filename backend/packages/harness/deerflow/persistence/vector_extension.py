"""Database vector-extension wiring for SQLite development/runtime."""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine


def register_sqlite_vec(engine: AsyncEngine) -> None:
    """Load sqlite-vec on every DB-API connection owned by an async engine."""
    if getattr(engine.sync_engine, "_deerflow_sqlite_vec_registered", False):
        return

    import sqlite_vec

    @event.listens_for(engine.sync_engine, "connect")
    def _load_sqlite_vec(dbapi_connection, _connection_record) -> None:  # noqa: ANN001, ARG001
        async def _load(driver_connection) -> None:  # noqa: ANN001
            await driver_connection.enable_load_extension(True)
            try:
                await driver_connection.load_extension(sqlite_vec.loadable_path())
            finally:
                await driver_connection.enable_load_extension(False)

        dbapi_connection.run_async(_load)

    setattr(engine.sync_engine, "_deerflow_sqlite_vec_registered", True)
