"""SQL persistence for automatic evaluations; no application-layer imports."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class EvaluationRepository:
    def __init__(self, session_factory):
        self._sf = session_factory

    async def create(self, *, actor_id: str, request_key: str, cases: list[dict], environment: dict, parent_id: str | None = None) -> dict:
        if not cases or len(cases) > 100 or len({case["id"] for case in cases}) != len(cases):
            raise ValueError("A nonempty set of unique cases is required")
        specification = {"cases": cases, "parent_id": parent_id}
        run_id = str(uuid.uuid4())
        async with self._sf() as session:
            try:
                await session.execute(
                    text("""INSERT INTO wu_evaluation_runs
                    (id,status,total,passed,pass_rate,created_by,created_at,execution_mode,request_key,spec_json,environment_json,parent_id)
                    VALUES (:id,'queued',:total,0,0,:actor,:now,'replay',:key,:spec,:environment,:parent)"""),
                    {"id": run_id, "total": len(cases), "actor": actor_id, "now": datetime.now(UTC), "key": request_key, "spec": _json(specification), "environment": _json(environment), "parent": parent_id},
                )
                for case in cases:
                    await session.execute(
                        text("""INSERT INTO wu_evaluation_attempts
                        (id,evaluation_run_id,case_id,case_json) VALUES (:id,:run,:case,:body)"""),
                        {"id": str(uuid.uuid4()), "run": run_id, "case": case["id"], "body": _json(case)},
                    )
                await session.commit()
            except IntegrityError:
                await session.rollback()
                row = (await session.execute(text("SELECT id,spec_json FROM wu_evaluation_runs WHERE created_by=:actor AND request_key=:key"), {"actor": actor_id, "key": request_key})).mappings().first()
                if row is None:
                    raise
                if json.loads(row["spec_json"]) != specification:
                    raise ValueError("idempotency key already used with another specification") from None
                run_id = row["id"]
        return await self.get(run_id)

    async def get(self, run_id: str) -> dict | None:
        async with self._sf() as session:
            row = (await session.execute(text("SELECT * FROM wu_evaluation_runs WHERE id=:id AND execution_mode='replay'"), {"id": run_id})).mappings().first()
            if row is None:
                return None
            result = dict(row)
            result["spec"] = json.loads(result.pop("spec_json"))
            result["environment"] = json.loads(result.pop("environment_json"))
            result["cancel_requested"] = bool(result["cancel_requested"])
            attempts = (await session.execute(text("SELECT * FROM wu_evaluation_attempts WHERE evaluation_run_id=:id ORDER BY case_id"), {"id": run_id})).mappings().all()
            result["results"] = [
                {
                    "attempt_id": item["id"],
                    "case_id": item["case_id"],
                    "case": json.loads(item["case_json"]),
                    **(json.loads(item["result_json"]) if item["result_json"] else {"status": "queued", "verdict": None, "checks": [], "events": [], "evidence": []}),
                }
                for item in attempts
            ]
            result["reviews"] = [dict(item) for item in (await session.execute(text("SELECT * FROM wu_evaluation_reviews WHERE evaluation_run_id=:id ORDER BY created_at,id"), {"id": run_id})).mappings().all()]
            result["counts"] = {
                key: sum((item.get("verdict") == key if key in {"passed", "failed", "needs_review"} else item.get("status") == key) for item in result["results"])
                for key in ("passed", "failed", "needs_review", "queued", "completed", "error", "cancelled", "skipped")
            }
            return result

    async def list(self, *, limit: int = 20, offset: int = 0) -> list[dict]:
        async with self._sf() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            """SELECT id,status,total,passed,pass_rate,created_at,started_at,finished_at,
                            parent_id,execution_mode,cancel_requested,error_message FROM wu_evaluation_runs
                            WHERE execution_mode='replay' ORDER BY created_at DESC,id DESC LIMIT :limit OFFSET :offset"""
                        ),
                        {"limit": limit, "offset": offset},
                    )
                )
                .mappings()
                .all()
            )
        # Polling the batch list must not repeatedly transfer every stored trace.
        return [{**dict(row), "cancel_requested": bool(row["cancel_requested"])} for row in rows]

    async def claim(self, *, owner: str, now: datetime | None = None) -> dict | None:
        now = now or datetime.now(UTC)
        timestamp = now.timestamp()
        async with self._sf() as session:
            # One singleton CAS serializes claims on SQLite and PostgreSQL alike.
            locked = await session.execute(text("UPDATE wu_evaluation_worker SET owner=:owner,lease_until=:until WHERE id=1 AND lease_until<=:now"), {"owner": owner, "until": timestamp + 45, "now": timestamp})
            if locked.rowcount != 1:
                await session.rollback()
                return None
            previous = (await session.execute(text("SELECT run_id FROM wu_evaluation_worker WHERE id=1"))).scalar_one_or_none()
            if previous:
                await self._finish_in_session(session, previous, state="error", error="Worker lease expired; execution was interrupted. Rerun creates a new attempt.")
            run_id = (await session.execute(text("SELECT id FROM wu_evaluation_runs WHERE execution_mode='replay' AND status='queued' AND cancel_requested=:false ORDER BY created_at,id LIMIT 1"), {"false": False})).scalar_one_or_none()
            if run_id is None:
                await session.execute(text("UPDATE wu_evaluation_worker SET owner=NULL,run_id=NULL,lease_until=0 WHERE id=1"))
            else:
                await session.execute(text("UPDATE wu_evaluation_worker SET run_id=:id WHERE id=1"), {"id": run_id})
                await session.execute(text("UPDATE wu_evaluation_runs SET status='running',started_at=:now WHERE id=:id"), {"id": run_id, "now": now.isoformat()})
            await session.commit()
        return await self.get(run_id) if run_id else None

    async def _guard(self, session, run_id: str, owner: str) -> None:
        result = await session.execute(text("UPDATE wu_evaluation_worker SET owner=:owner WHERE id=1 AND owner=:owner AND run_id=:run AND lease_until>:now"), {"owner": owner, "run": run_id, "now": datetime.now(UTC).timestamp()})
        if result.rowcount != 1:
            raise ValueError("Evaluation worker lease was lost")

    async def heartbeat(self, run_id: str, *, owner: str) -> bool:
        async with self._sf() as session:
            now = datetime.now(UTC).timestamp()
            result = await session.execute(text("UPDATE wu_evaluation_worker SET lease_until=:until WHERE id=1 AND owner=:owner AND run_id=:run AND lease_until>:now"), {"until": now + 45, "owner": owner, "run": run_id, "now": now})
            await session.commit()
            return result.rowcount == 1

    async def record_result(self, run_id: str, *, case_id: str, result: dict, owner: str) -> None:
        async with self._sf() as session:
            await self._guard(session, run_id, owner)
            await session.execute(text("UPDATE wu_evaluation_attempts SET result_json=:body WHERE evaluation_run_id=:run AND case_id=:case AND result_json IS NULL"), {"run": run_id, "case": case_id, "body": _json(result)})
            rows = (await session.execute(text("SELECT result_json FROM wu_evaluation_attempts WHERE evaluation_run_id=:id AND result_json IS NOT NULL"), {"id": run_id})).scalars().all()
            passed = sum(json.loads(row).get("verdict") == "passed" for row in rows)
            await session.execute(text("UPDATE wu_evaluation_runs SET passed=:passed,pass_rate=CAST(:passed AS FLOAT)/total WHERE id=:id"), {"passed": passed, "id": run_id})
            await session.commit()

    async def record_environment(self, run_id: str, *, environment: dict, owner: str) -> None:
        async with self._sf() as session:
            await self._guard(session, run_id, owner)
            current = (await session.execute(text("SELECT environment_json FROM wu_evaluation_runs WHERE id=:id"), {"id": run_id})).scalar_one()
            await session.execute(text("UPDATE wu_evaluation_runs SET environment_json=:body WHERE id=:id"), {"id": run_id, "body": _json({**json.loads(current), "corpus": environment})})
            await session.commit()

    async def cancel(self, run_id: str) -> None:
        async with self._sf() as session:
            row = (await session.execute(text("SELECT status FROM wu_evaluation_runs WHERE id=:id AND execution_mode='replay'"), {"id": run_id})).scalar_one_or_none()
            if row is None:
                raise ValueError("Evaluation not found")
            if row in {"queued", "running"}:
                await session.execute(text("UPDATE wu_evaluation_runs SET cancel_requested=:true WHERE id=:id"), {"true": True, "id": run_id})
                if row == "queued":
                    await self._finish_in_session(session, run_id, state="cancelled", error="Cancelled before execution")
            await session.commit()

    async def _finish_in_session(self, session, run_id: str, *, state: str, error: str | None) -> None:
        incomplete = "cancelled" if state == "cancelled" else "error"
        await session.execute(
            text("UPDATE wu_evaluation_attempts SET result_json=:body WHERE evaluation_run_id=:id AND result_json IS NULL"),
            {"id": run_id, "body": _json({"status": incomplete, "verdict": None, "error": error or "Execution produced no result", "checks": [], "events": [], "evidence": []})},
        )
        await session.execute(
            text("UPDATE wu_evaluation_runs SET status=:state,error_message=:error,finished_at=:now WHERE id=:id AND status IN ('queued','running')"), {"state": state, "error": error, "id": run_id, "now": datetime.now(UTC).isoformat()}
        )

    async def finish(self, run_id: str, *, owner: str, error: str | None = None) -> None:
        async with self._sf() as session:
            await self._guard(session, run_id, owner)
            cancelled = (await session.execute(text("SELECT cancel_requested FROM wu_evaluation_runs WHERE id=:id"), {"id": run_id})).scalar_one()
            rows = (await session.execute(text("SELECT result_json FROM wu_evaluation_attempts WHERE evaluation_run_id=:id"), {"id": run_id})).scalars().all()
            has_error = any(row is None or json.loads(row).get("status") == "error" for row in rows)
            state = "cancelled" if cancelled else ("error" if error or has_error else "completed")
            await self._finish_in_session(session, run_id, state=state, error=error)
            await session.execute(text("UPDATE wu_evaluation_worker SET owner=NULL,run_id=NULL,lease_until=0 WHERE id=1"))
            await session.commit()

    async def add_review(self, run_id: str, *, case_id: str, actor_id: str, decision: str, note: str) -> None:
        if decision not in {"confirmed", "disagreed", "needs_review"} or not note.strip():
            raise ValueError("A review decision and note are required")
        async with self._sf() as session:
            result = (await session.execute(text("SELECT result_json FROM wu_evaluation_attempts WHERE evaluation_run_id=:run AND case_id=:case"), {"run": run_id, "case": case_id})).scalar_one_or_none()
            if result is None:
                raise ValueError("Completed observation not found")
            await session.execute(
                text("INSERT INTO wu_evaluation_reviews (id,evaluation_run_id,case_id,actor_id,decision,note,created_at) VALUES (:id,:run,:case,:actor,:decision,:note,:now)"),
                {"id": str(uuid.uuid4()), "run": run_id, "case": case_id, "actor": actor_id, "decision": decision, "note": note.strip(), "now": datetime.now(UTC)},
            )
            await session.commit()
