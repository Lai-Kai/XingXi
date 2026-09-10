from __future__ import annotations

import math
import sqlite3
import time


def test_sqlite_trigram_query_p95_is_below_product_target() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE documents (id INTEGER PRIMARY KEY, search_title TEXT, search_headings TEXT, search_body TEXT)")
        connection.execute("CREATE VIRTUAL TABLE fulltext USING fts5(search_title, search_headings, search_body, content='documents', content_rowid='id', tokenize='trigram')")
        connection.executemany(
            "INSERT INTO documents(search_title, search_headings, search_body) VALUES (?, ?, ?)",
            (
                (
                    f"木渎资料 {index}",
                    "卷一 桥梁" if index % 50 == 0 else "卷二 风俗",
                    f"第 {index} 条。香溪沿岸古桥旧名虹桥。" if index % 50 == 0 else f"第 {index} 条普通地方志文本。",
                )
                for index in range(10_000)
            ),
        )
        connection.execute("INSERT INTO fulltext(fulltext) VALUES('rebuild')")
        query = '"香溪沿岸"'
        statement = "SELECT rowid FROM fulltext WHERE fulltext MATCH ? LIMIT 20"
        connection.execute(statement, (query,)).fetchall()

        durations = []
        for _ in range(50):
            started = time.perf_counter()
            rows = connection.execute(statement, (query,)).fetchall()
            durations.append(time.perf_counter() - started)
        p95 = sorted(durations)[math.ceil(len(durations) * 0.95) - 1]

        assert len(rows) == 20
        assert p95 <= 1.5
    finally:
        connection.close()
