#!/usr/bin/env python3
"""Migrate one DeerFlow SQLite database into an empty PostgreSQL database.

Application tables are copied against the live PostgreSQL schema. LangGraph
checkpoints and Store items are re-serialized through their public APIs because
their SQLite and PostgreSQL table layouts are intentionally different.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import struct
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

SQLITE_CHECKPOINTER_TABLES = frozenset(
    {
        "checkpoints",
        "writes",
        "checkpoint_blobs",
        "checkpoint_writes",
        "checkpoint_migrations",
    }
)
SQLITE_STORE_TABLES = frozenset({"store", "store_migrations"})
ALWAYS_EXCLUDED_TABLES = frozenset({"alembic_version"})
POSTGRES_RUNTIME_DATA_TABLES = (
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "store",
)


class SQLiteInventory(NamedTuple):
    application_tables: tuple[str, ...]
    checkpointer_tables: tuple[str, ...]
    store_tables: tuple[str, ...]
    excluded_tables: tuple[str, ...]


def _connect_sqlite_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def inspect_sqlite(path: Path) -> SQLiteInventory:
    """Classify source tables without importing application packages."""
    with _connect_sqlite_readonly(path) as connection:
        rows = connection.execute(
            "SELECT name, COALESCE(sql, '') AS sql FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()

    names = {str(row["name"]) for row in rows if not str(row["name"]).startswith("sqlite_")}
    virtual_roots = {
        str(row["name"])
        for row in rows
        if "CREATE VIRTUAL TABLE" in str(row["sql"]).upper()
    }
    virtual_tables = {
        name
        for name in names
        if any(name == root or name.startswith(f"{root}_") for root in virtual_roots)
    }
    checkpointer = tuple(
        name
        for name in (
            "checkpoints",
            "checkpoint_blobs",
            "checkpoint_writes",
            "writes",
            "checkpoint_migrations",
        )
        if name in names
    )
    store = tuple(name for name in ("store", "store_migrations") if name in names)
    excluded = tuple(sorted(virtual_tables | (names & ALWAYS_EXCLUDED_TABLES)))
    application = tuple(sorted(names - set(checkpointer) - set(store) - set(excluded)))
    return SQLiteInventory(application, checkpointer, store, excluded)


def _table_counts(path: Path, tables: tuple[str, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    with _connect_sqlite_readonly(path) as connection:
        for table in tables:
            quoted = table.replace('"', '""')
            counts[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0])
    return counts


def build_dry_run_report(path: Path) -> dict[str, Any]:
    inventory = inspect_sqlite(path)
    application_counts = _table_counts(path, inventory.application_tables)
    checkpointer_counts = _table_counts(path, inventory.checkpointer_tables)
    store_counts = _table_counts(path, inventory.store_tables)
    return {
        "mode": "dry-run",
        "created_at": datetime.now(UTC).isoformat(),
        "source": {
            "sqlite_path": str(path.resolve()),
            "application_counts": application_counts,
            "checkpointer_counts": checkpointer_counts,
            "store_counts": store_counts,
            "excluded_tables": list(inventory.excluded_tables),
            "total_application_rows": sum(application_counts.values()),
        },
    }


def _validate_sqlite(path: Path) -> None:
    with _connect_sqlite_readonly(path) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: {integrity}")
        violations = connection.execute("PRAGMA foreign_key_check").fetchmany(20)
        if violations:
            formatted = [tuple(row) for row in violations]
            raise RuntimeError(f"SQLite foreign_key_check failed (first 20): {formatted!r}")


def _postgres_urls(raw_url: str) -> tuple[str, str]:
    from sqlalchemy.engine import make_url

    parsed = make_url(raw_url)
    if not parsed.drivername.startswith("postgresql"):
        raise ValueError("--postgres-url must use a postgresql scheme")
    psycopg_url = parsed.set(drivername="postgresql").render_as_string(hide_password=False)
    asyncpg_url = parsed.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)
    return psycopg_url, asyncpg_url


async def _bootstrap_target(asyncpg_url: str, psycopg_url: str) -> None:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.store.postgres.aio import AsyncPostgresStore
    from sqlalchemy.ext.asyncio import create_async_engine

    from deerflow.persistence.bootstrap import bootstrap_schema

    engine = create_async_engine(asyncpg_url, pool_pre_ping=True)
    try:
        await bootstrap_schema(engine, backend="postgres")
    finally:
        await engine.dispose()

    async with AsyncPostgresSaver.from_conn_string(psycopg_url) as saver:
        await saver.setup()
    async with AsyncPostgresStore.from_conn_string(psycopg_url) as store:
        await store.setup()


def _postgres_table_columns(connection, table: str) -> list[dict[str, str | None]]:
    rows = connection.execute(
        """
        SELECT column_name, data_type, udt_name, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    ).fetchall()
    return [
        {
            "name": row[0],
            "data_type": row[1],
            "udt_name": row[2],
            "nullable": row[3],
            "default": row[4],
        }
        for row in rows
    ]


def _postgres_application_tables(connection) -> set[str]:
    rows = connection.execute(
        "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'"
    ).fetchall()
    runtime = set(POSTGRES_RUNTIME_DATA_TABLES) | {"checkpoint_migrations", "store_migrations", "alembic_version"}
    return {row[0] for row in rows} - runtime


def _assert_empty_target(connection, application_tables: tuple[str, ...]) -> None:
    from psycopg import sql

    occupied: dict[str, int] = {}
    for table in (*application_tables, *POSTGRES_RUNTIME_DATA_TABLES):
        columns = _postgres_table_columns(connection, table)
        if not columns:
            if table in application_tables:
                raise RuntimeError(f"PostgreSQL target is missing application table {table!r}")
            continue
        count = int(connection.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))).fetchone()[0])
        if count:
            occupied[table] = count
    if occupied:
        raise RuntimeError(f"PostgreSQL target must be empty; found rows: {occupied!r}")


def _remove_known_bootstrap_seeds(connection) -> None:
    """Remove only immutable empty-state rows inserted by the migration chain."""
    rows = connection.execute(
        """
        SELECT id, active_release_id, state_version, updated_by, updated_at
        FROM wu_knowledge_release_state
        """
    ).fetchall()
    if not rows:
        return
    expected = [("active", None, 0, None, None)]
    if rows != expected:
        raise RuntimeError(
            "PostgreSQL target contains a non-empty knowledge release state; "
            f"refusing to overwrite it: {rows!r}"
        )
    connection.execute("DELETE FROM wu_knowledge_release_state WHERE id = 'active'")


def _ordered_application_tables(connection, source_tables: tuple[str, ...]) -> tuple[str, ...]:
    target_tables = _postgres_application_tables(connection)
    missing = set(source_tables) - target_tables
    if missing:
        raise RuntimeError(f"PostgreSQL target is missing source tables: {sorted(missing)!r}")

    rows = connection.execute(
        """
        SELECT tc.table_name, ccu.table_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_catalog = tc.constraint_catalog
         AND ccu.constraint_schema = tc.constraint_schema
         AND ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
        """
    ).fetchall()
    source = set(source_tables)
    dependencies: dict[str, set[str]] = {table: set() for table in source_tables}
    for child, parent in rows:
        if child in source and parent in source and child != parent:
            dependencies[child].add(parent)

    ordered: list[str] = []
    remaining = set(source_tables)
    while remaining:
        ready = sorted(table for table in remaining if not (dependencies[table] & remaining))
        if not ready:
            raise RuntimeError(f"Cannot order tables because of a foreign-key cycle: {sorted(remaining)!r}")
        ordered.extend(ready)
        remaining.difference_update(ready)
    return tuple(ordered)


def _decode_vector(value: Any) -> Any:
    if value is None or isinstance(value, (list, tuple)):
        return value
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        if len(value) % 4:
            raise ValueError(f"invalid float32 vector payload length: {len(value)}")
        return list(struct.unpack(f"<{len(value) // 4}f", value))
    if isinstance(value, str):
        return json.loads(value)
    return value


def _convert_value(value: Any, column: dict[str, str | None]) -> Any:
    if value is None:
        return None
    data_type = column["data_type"]
    udt_name = column["udt_name"]
    if data_type == "boolean":
        return bool(value)
    if data_type in {"json", "jsonb"}:
        from psycopg.types.json import Json, Jsonb

        if isinstance(value, memoryview):
            value = value.tobytes()
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        parsed = json.loads(value) if isinstance(value, str) else value
        return Jsonb(parsed) if data_type == "jsonb" else Json(parsed)
    if udt_name == "vector":
        return _decode_vector(value)
    if data_type == "bytea" and isinstance(value, memoryview):
        return value.tobytes()
    return value


def _copy_application_tables(
    sqlite_path: Path,
    psycopg_url: str,
    tables: tuple[str, ...],
    *,
    batch_size: int,
) -> dict[str, int]:
    import psycopg
    from pgvector.psycopg import register_vector
    from psycopg import sql

    copied: dict[str, int] = {}
    with _connect_sqlite_readonly(sqlite_path) as source, psycopg.connect(psycopg_url) as target:
        register_vector(target)
        _remove_known_bootstrap_seeds(target)
        _assert_empty_target(target, tables)
        ordered = _ordered_application_tables(target, tables)
        for table in ordered:
            target_columns = _postgres_table_columns(target, table)
            source_info = source.execute(f'PRAGMA table_info("{table.replace(chr(34), chr(34) * 2)}")').fetchall()
            source_columns = {str(row["name"]) for row in source_info}
            columns = [column for column in target_columns if str(column["name"]) in source_columns]
            missing_required = [
                str(column["name"])
                for column in target_columns
                if column["name"] not in source_columns
                and column["nullable"] == "NO"
                and column["default"] is None
            ]
            if missing_required:
                raise RuntimeError(f"{table}: source lacks required target columns {missing_required!r}")

            names = [str(column["name"]) for column in columns]
            quoted_source_columns = ", ".join(f'"{name.replace(chr(34), chr(34) * 2)}"' for name in names)
            source_cursor = source.execute(
                f'SELECT {quoted_source_columns} FROM "{table.replace(chr(34), chr(34) * 2)}"'
            )
            copy_statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
                sql.Identifier(table),
                sql.SQL(", ").join(sql.Identifier(name) for name in names),
            )
            count = 0
            with target.cursor().copy(copy_statement) as copy:
                while rows := source_cursor.fetchmany(batch_size):
                    for row in rows:
                        copy.write_row(tuple(_convert_value(row[name], column) for name, column in zip(names, columns, strict=True)))
                        count += 1
            copied[table] = count

        for table in ordered:
            for column in _postgres_table_columns(target, table):
                sequence = target.execute(
                    "SELECT pg_get_serial_sequence(%s, %s)", (f"public.{table}", column["name"])
                ).fetchone()[0]
                if not sequence:
                    continue
                maximum = target.execute(
                    sql.SQL("SELECT MAX({}) FROM {}").format(
                        sql.Identifier(str(column["name"])), sql.Identifier(table)
                    )
                ).fetchone()[0]
                if maximum is not None:
                    target.execute("SELECT setval(%s, %s, true)", (sequence, maximum))
        target.commit()
    return copied


async def _migrate_checkpoints(sqlite_path: Path, psycopg_url: str) -> tuple[int, int]:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    source_items = []
    async with AsyncSqliteSaver.from_conn_string(str(sqlite_path)) as source:
        await source.setup()
        source_items = [item async for item in source.alist(None)]

    source_items.sort(
        key=lambda item: (
            str(item.config["configurable"]["thread_id"]),
            str(item.config["configurable"].get("checkpoint_ns", "")),
            str(item.config["configurable"]["checkpoint_id"]),
        )
    )
    async with AsyncPostgresSaver.from_conn_string(psycopg_url) as target:
        await target.setup()
        for item in source_items:
            configurable = item.config["configurable"]
            parent_config = item.parent_config or {
                "configurable": {
                    "thread_id": configurable["thread_id"],
                    "checkpoint_ns": configurable.get("checkpoint_ns", ""),
                }
            }
            await target.aput(
                parent_config,
                item.checkpoint,
                item.metadata,
                item.checkpoint.get("channel_versions", {}),
            )
            writes_by_task: dict[str, list[tuple[str, Any]]] = defaultdict(list)
            for task_id, channel, value in item.pending_writes or []:
                writes_by_task[task_id].append((channel, value))
            for task_id, writes in writes_by_task.items():
                await target.aput_writes(item.config, writes, task_id)

        target_count = 0
        async for _ in target.alist(None):
            target_count += 1
    return len(source_items), target_count


async def _count_checkpoints(sqlite_path: Path, psycopg_url: str) -> tuple[int, int]:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    async with AsyncSqliteSaver.from_conn_string(str(sqlite_path)) as source:
        await source.setup()
        source_count = 0
        async for _ in source.alist(None):
            source_count += 1
    async with AsyncPostgresSaver.from_conn_string(psycopg_url) as target:
        await target.setup()
        target_count = 0
        async for _ in target.alist(None):
            target_count += 1
    return source_count, target_count


async def _read_store_items(store) -> list[Any]:
    namespaces: list[tuple[str, ...]] = []
    offset = 0
    while True:
        page = await store.alist_namespaces(limit=100, offset=offset)
        namespaces.extend(page)
        if len(page) < 100:
            break
        offset += len(page)

    items: dict[tuple[tuple[str, ...], str], Any] = {}
    for namespace in namespaces:
        offset = 0
        while True:
            page = await store.asearch(namespace, limit=100, offset=offset)
            exact = [item for item in page if tuple(item.namespace) == tuple(namespace)]
            for item in exact:
                items[(tuple(item.namespace), item.key)] = item
            if len(page) < 100:
                break
            offset += len(page)
    return list(items.values())


async def _migrate_store(sqlite_path: Path, psycopg_url: str) -> tuple[int, int]:
    from langgraph.store.postgres.aio import AsyncPostgresStore
    from langgraph.store.sqlite.aio import AsyncSqliteStore

    async with AsyncSqliteStore.from_conn_string(str(sqlite_path)) as source:
        await source.setup()
        source_items = await _read_store_items(source)

    async with AsyncPostgresStore.from_conn_string(psycopg_url) as target:
        await target.setup()
        for item in source_items:
            await target.aput(tuple(item.namespace), item.key, item.value)
        target_items = await _read_store_items(target)
    return len(source_items), len(target_items)


async def _count_store(sqlite_path: Path, psycopg_url: str) -> tuple[int, int]:
    from langgraph.store.postgres.aio import AsyncPostgresStore
    from langgraph.store.sqlite.aio import AsyncSqliteStore

    async with AsyncSqliteStore.from_conn_string(str(sqlite_path)) as source:
        await source.setup()
        source_items = await _read_store_items(source)
    async with AsyncPostgresStore.from_conn_string(psycopg_url) as target:
        await target.setup()
        target_items = await _read_store_items(target)
    return len(source_items), len(target_items)


def _postgres_counts(psycopg_url: str, tables: tuple[str, ...]) -> dict[str, int]:
    import psycopg
    from psycopg import sql

    with psycopg.connect(psycopg_url) as connection:
        return {
            table: int(
                connection.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))).fetchone()[0]
            )
            for table in tables
        }


async def migrate(sqlite_path: Path, postgres_url: str, *, batch_size: int) -> dict[str, Any]:
    _validate_sqlite(sqlite_path)
    inventory = inspect_sqlite(sqlite_path)
    source_counts = _table_counts(sqlite_path, inventory.application_tables)
    psycopg_url, asyncpg_url = _postgres_urls(postgres_url)

    await _bootstrap_target(asyncpg_url, psycopg_url)
    copied_counts = await asyncio.to_thread(
        _copy_application_tables,
        sqlite_path,
        psycopg_url,
        inventory.application_tables,
        batch_size=batch_size,
    )
    checkpoint_source, checkpoint_target = await _migrate_checkpoints(sqlite_path, psycopg_url)
    store_source, store_target = await _migrate_store(sqlite_path, psycopg_url)
    target_counts = await asyncio.to_thread(_postgres_counts, psycopg_url, inventory.application_tables)

    mismatches = {
        table: {"source": source_counts[table], "target": target_counts.get(table)}
        for table in inventory.application_tables
        if source_counts[table] != target_counts.get(table)
    }
    if checkpoint_source != checkpoint_target:
        mismatches["checkpoints"] = {"source": checkpoint_source, "target": checkpoint_target}
    if store_source != store_target:
        mismatches["store"] = {"source": store_source, "target": store_target}

    report = {
        "mode": "migration",
        "created_at": datetime.now(UTC).isoformat(),
        "source": {
            "sqlite_path": str(sqlite_path.resolve()),
            "application_counts": source_counts,
            "excluded_tables": list(inventory.excluded_tables),
        },
        "target": {
            "application_counts": target_counts,
            "checkpoint_count": checkpoint_target,
            "store_count": store_target,
        },
        "copied_application_counts": copied_counts,
        "mismatches": mismatches,
        "verified": not mismatches,
    }
    if mismatches:
        raise RuntimeError(f"migration verification failed: {mismatches!r}")
    return report


async def verify_existing(sqlite_path: Path, postgres_url: str) -> dict[str, Any]:
    """Verify a populated target after an interrupted post-copy validation."""
    _validate_sqlite(sqlite_path)
    inventory = inspect_sqlite(sqlite_path)
    source_counts = _table_counts(sqlite_path, inventory.application_tables)
    psycopg_url, _ = _postgres_urls(postgres_url)
    target_counts = await asyncio.to_thread(_postgres_counts, psycopg_url, inventory.application_tables)
    checkpoint_source, checkpoint_target = await _count_checkpoints(sqlite_path, psycopg_url)
    store_source, store_target = await _count_store(sqlite_path, psycopg_url)

    mismatches = {
        table: {"source": source_counts[table], "target": target_counts.get(table)}
        for table in inventory.application_tables
        if source_counts[table] != target_counts.get(table)
    }
    if checkpoint_source != checkpoint_target:
        mismatches["checkpoints"] = {"source": checkpoint_source, "target": checkpoint_target}
    if store_source != store_target:
        mismatches["store"] = {"source": store_source, "target": store_target}

    report = {
        "mode": "verify-only",
        "created_at": datetime.now(UTC).isoformat(),
        "source": {
            "sqlite_path": str(sqlite_path.resolve()),
            "application_counts": source_counts,
            "checkpoint_count": checkpoint_source,
            "store_count": store_source,
            "excluded_tables": list(inventory.excluded_tables),
        },
        "target": {
            "application_counts": target_counts,
            "checkpoint_count": checkpoint_target,
            "store_count": store_target,
        },
        "mismatches": mismatches,
        "verified": not mismatches,
    }
    if mismatches:
        raise RuntimeError(f"migration verification failed: {mismatches!r}")
    return report


def _write_report(report: dict[str, Any], path: Path | None) -> None:
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-path", type=Path, required=True)
    parser.add_argument("--postgres-url", default=os.environ.get("DATABASE_URL", ""))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--verify-only", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--batch-size", type=int, default=1000)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    if not args.sqlite_path.is_file():
        raise FileNotFoundError(args.sqlite_path)
    if args.batch_size < 1:
        raise ValueError("--batch-size must be positive")
    if args.dry_run:
        report = build_dry_run_report(args.sqlite_path)
    else:
        if not args.postgres_url:
            raise ValueError("--postgres-url or DATABASE_URL is required unless --dry-run is used")
        if args.verify_only:
            report = asyncio.run(verify_existing(args.sqlite_path, args.postgres_url))
        else:
            report = asyncio.run(migrate(args.sqlite_path, args.postgres_url, batch_size=args.batch_size))
    _write_report(report, args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
