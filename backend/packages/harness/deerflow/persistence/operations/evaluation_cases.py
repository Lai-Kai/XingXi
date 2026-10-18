"""SQL storage of custom automatic cases and built-in activation overrides."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


class EvaluationCaseRepository:
    def __init__(self, session_factory):
        self._sf = session_factory

    async def list(self) -> list[dict]:
        async with self._sf() as session:
            rows = (await session.execute(text("SELECT case_id,case_json,active FROM wu_agent_evaluation_cases ORDER BY created_at,case_id"))).mappings().all()
        return [{"id": row["case_id"], "case": json.loads(row["case_json"]) if row["case_json"] else None, "active": bool(row["active"])} for row in rows]

    async def create(self, *, case: dict, actor_id: str) -> None:
        async with self._sf() as session:
            await session.execute(
                text("""INSERT INTO wu_agent_evaluation_cases
                (case_id,case_json,active,created_by,created_at,updated_by,updated_at)
                VALUES (:id,:body,:active,:actor,:now,:actor,:now)"""),
                {"id": case["id"], "body": json.dumps(case, ensure_ascii=False), "active": True, "actor": actor_id, "now": datetime.now(UTC)},
            )
            await session.commit()

    async def set_active(self, case_id: str, *, active: bool, actor_id: str) -> None:
        values = {"id": case_id, "active": active, "actor": actor_id, "now": datetime.now(UTC)}
        statement = text("UPDATE wu_agent_evaluation_cases SET active=:active,updated_by=:actor,updated_at=:now WHERE case_id=:id")
        async with self._sf() as session:
            result = await session.execute(statement, values)
            if result.rowcount == 0:
                try:
                    await session.execute(
                        text("""INSERT INTO wu_agent_evaluation_cases
                        (case_id,case_json,active,created_by,created_at,updated_by,updated_at)
                        VALUES (:id,NULL,:active,:actor,:now,:actor,:now)"""),
                        values,
                    )
                except IntegrityError:
                    # Two workers may create the first built-in override together.
                    await session.rollback()
                    await session.execute(statement, values)
            await session.commit()
