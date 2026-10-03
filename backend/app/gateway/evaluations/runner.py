"""Execute frozen cases through a real, isolated Gateway (no listening port)."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import tempfile
import time
import traceback
import uuid
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from app.gateway.evaluations.suites import EvaluationCase


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, default=str), encoding="utf-8")
    temporary.replace(path)


def configure(home: Path) -> None:
    """Override every external service boundary before importing the Gateway."""
    (home / "skills/public").mkdir(parents=True)
    (home / "skills/custom").mkdir(parents=True)
    config = {
        "log_level": "warning",
        "models": [{"name": "evaluation-replay", "model": "xingxi-synthetic-replay-v1", "use": "app.gateway.evaluations.replay_model:SyntheticReplayModel", "supports_thinking": True}],
        "database": {"backend": "sqlite", "sqlite_dir": str(home / "db")},
        "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
        "skills": {"path": str(home / "skills"), "container_path": "/mnt/skills"},
        "tools": [],
        "tool_groups": [],
        "memory": {"enabled": False, "injection_enabled": False, "token_counting": "char"},
        "summarization": {"enabled": False},
        "title": {"enabled": False},
        "scheduler": {"enabled": False},
        "embedding": {"enabled": False},
        "evidence_pack": {"token_counting": "char"},
        "run_events": {"backend": "db", "max_trace_content": 100000},
    }
    path = home / "config.yaml"
    path.write_text(json.dumps(config), encoding="utf-8")
    extensions = home / "extensions_config.json"
    extensions.write_text('{"mcpServers":{},"skills":{}}', encoding="utf-8")
    os.environ.update(
        {
            "DEER_FLOW_HOME": str(home),
            "DEER_FLOW_PROJECT_ROOT": str(home),
            "DEER_FLOW_CONFIG_PATH": str(path),
            "DEER_FLOW_EXTENSIONS_CONFIG_PATH": str(extensions),
            "XINGXI_EVALUATION_CHILD": "1",
            "PYTHON_DOTENV_DISABLED": "1",
            "DEER_FLOW_AUTH_DISABLED": "0",
            "AUTH_JWT_SECRET": secrets.token_hex(32),
            "GATEWAY_WORKERS": "1",
            "LANGFUSE_TRACING": "false",
            "LANGSMITH_TRACING": "false",
            "MONOCLE_TRACING": "false",
        }
    )


def _require(response):
    if not response.is_success:
        raise RuntimeError(f"Gateway request failed ({response.status_code}): {response.text[:500]}")
    return response.json() if response.content else None


def _project_events(events: list[dict]) -> tuple[list[dict], list[dict]]:
    timeline, evidence = [], {}
    for event in events:
        kind = event.get("event_type")
        content = event.get("content", {})
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except ValueError:
                content = {}
        base = {"seq": event.get("seq"), "at": event.get("created_at"), "event_type": kind}
        if kind == "llm.ai.response":
            for call in content.get("tool_calls", []):
                timeline.append({**base, "type": "tool_call", "name": call.get("name"), "args": call.get("args"), "tool_call_id": call.get("id")})
        elif kind == "llm.tool.result":
            output = content.get("content", "")
            try:
                output = json.loads(output) if isinstance(output, str) else output
            except ValueError:
                pass
            timeline.append({**base, "type": "tool_result", "name": content.get("name"), "output": output, "tool_call_id": content.get("tool_call_id")})
            if isinstance(output, dict):
                for item in output.get("evidence_pack", {}).get("items", []):
                    evidence[item["evidence_id"]] = item
        elif kind in {"run.start", "run.end", "run.error", "llm.error"} or (isinstance(kind, str) and kind.startswith("middleware:")):
            timeline.append({**base, "type": kind})
    return timeline, list(evidence.values())


async def _verify_evidence(items: list[dict], release_id: str) -> list[dict]:
    from sqlalchemy import select
    from wu_culture import AuthorizedUse, evaluate_source_access

    from deerflow.persistence.engine import get_session_factory
    from deerflow.persistence.wu_culture import KnowledgeReleaseItemRow, SqlEvidenceRepository

    sf = get_session_factory()
    repository = SqlEvidenceRepository(sf)
    verified = []
    async with sf() as session:
        chunks = set((await session.execute(select(KnowledgeReleaseItemRow.chunk_id).where(KnowledgeReleaseItemRow.release_id == release_id))).scalars().all())
    for item in items:
        record = await repository.get_evidence(item["evidence_id"])
        allowed = record is not None and evaluate_source_access(record.document, use=AuthorizedUse.PUBLIC_QUOTE).allowed
        # Full-text search highlights query matches. Compare the visible quote
        # after removing that markup, and retain the stored original separately.
        quote = item["quote"].replace("【", "").replace("】", "").strip("…")
        valid = bool(
            record
            and allowed
            and record.chunk.id in chunks
            and item["chunk_id"] == record.chunk.id
            and item["document_id"] == record.document.id
            and item["page_start"] == record.chunk.page_start
            and item["page_end"] == record.chunk.page_end
            and quote
            and quote in record.chunk.normalized_text
        )
        verified.append({**item, "verified": valid, "release_id": release_id, "stored_quote": record.evidence.quote if record else None, "chunk_sha256": hashlib.sha256(record.chunk.normalized_text.encode()).hexdigest() if record else None})
    return verified


async def _await_run_finished(app, run_id: str) -> None:
    record = await app.state.run_manager.get(run_id)
    if record and record.task:
        # Status changes before the worker's finally block flushes RunJournal.
        await asyncio.wait_for(asyncio.shield(record.task), timeout=15)


def execute_case(client, case: EvaluationCase, release: dict, directory: Path) -> dict:
    from app.gateway.evaluations import replay_model
    from app.gateway.evaluations.corpus import configure_source
    from app.gateway.evaluations.grading import grade_attempt

    started = time.monotonic()
    observed = {"status": "error", "answer": "", "events": [], "evidence": [], "started_at": datetime.now(UTC).isoformat(), "expected_release_id": release["release_id"], "token_usage": None, "cost": None}
    replay_model.CURRENT_CASE = case
    replay_model.REPLAY_ERRORS.clear()
    replay_model.BOUND_TOOLS.clear()
    try:
        client.portal.call(partial(configure_source, revoked=case.scenario == "revoked"))
        thread_id = str(uuid.uuid4())
        _require(client.post("/api/threads", json={"thread_id": thread_id, "metadata": {"evaluation": True}}))
        observed["thread_id"] = thread_id
        prompts = [case.question, replay_model.FOLLOWUP] if case.scenario == "followup" else [case.question]
        run_ids, all_events = [], []
        for prompt in prompts:
            record = _require(
                client.post(
                    f"/api/threads/{thread_id}/runs",
                    json={
                        "assistant_id": "xingxi",
                        "input": {"messages": [{"role": "user", "content": prompt}]},
                        "context": {"mode": case.mode, "model_name": "evaluation-replay"},
                        "metadata": {"evaluation": True, "knowledge_release_id": "client-forged-release"},
                        "on_disconnect": "continue",
                        "stream_mode": ["values"],
                    },
                )
            )
            run_id = record["run_id"]
            run_ids.append(run_id)
            observed.update(agent_run_id=run_id, agent_run_ids=run_ids, release_id=record.get("metadata", {}).get("knowledge_release_id"))
            run_started = time.monotonic()
            cancelled = False
            while record["status"] in {"pending", "running"}:
                elapsed = time.monotonic() - run_started
                external_cancel = (directory / "cancel").exists()
                should_cancel = external_cancel or (case.scenario == "cancel" and elapsed > 0.3) or elapsed > case.timeout_seconds
                if should_cancel and not cancelled:
                    response = client.post(f"/api/threads/{thread_id}/runs/{run_id}/cancel?wait=true")
                    _require(response)
                    cancelled = True
                    observed["cancel_acknowledged"] = True
                    if external_cancel:
                        observed["status"] = "cancelled"
                    elif case.scenario not in {"cancel", "timeout"}:
                        observed["error"] = "Case exceeded its execution deadline"
                if elapsed > case.timeout_seconds + 15:
                    raise TimeoutError("Run did not stop after cancellation")
                time.sleep(0.05)
                record = _require(client.get(f"/api/threads/{thread_id}/runs/{run_id}"))
            observed["run_status"] = record["status"]
            client.portal.call(_await_run_finished, client.app, run_id)
            after = None
            while True:
                params = {"limit": 500}
                if after is not None:
                    params["after_seq"] = after
                events = _require(client.get(f"/api/threads/{thread_id}/runs/{run_id}/events", params=params))
                all_events.extend(events)
                if len(events) < 500:
                    break
                after = events[-1]["seq"]
            if cancelled:
                break
        state = _require(client.get(f"/api/threads/{thread_id}/state"))
        messages = state.get("values", {}).get("messages", [])
        final = [item for item in messages if item.get("type") in {"ai", "assistant"} and not item.get("tool_calls") and not item.get("additional_kwargs", {}).get("hide_from_ui")]
        if final:
            answer = final[-1].get("content", "")
            observed["answer"] = answer if isinstance(answer, str) else "\n".join(item.get("text", "") for item in answer if isinstance(item, dict))
        timeline, evidence = _project_events(all_events)
        observed["events"] = timeline
        observed["evidence"] = client.portal.call(_verify_evidence, evidence, observed.get("release_id"))
        observed["allowed_tools"] = replay_model.BOUND_TOOLS.copy()
        observed["replay_errors"] = replay_model.REPLAY_ERRORS.copy()
        if observed["status"] != "cancelled" and not observed.get("error"):
            observed["status"] = "completed"
    except Exception as exc:
        observed.update(status="error", error=f"{type(exc).__name__}: {exc}")
    observed.update(elapsed_ms=round((time.monotonic() - started) * 1000), finished_at=datetime.now(UTC).isoformat())
    return grade_attempt(case, observed)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    directory = arguments.output.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    try:
        specification = json.loads(arguments.spec.read_text())
        cases = [EvaluationCase.model_validate(case) for case in specification["cases"]]
        home = Path(tempfile.mkdtemp(prefix="runtime-", dir=directory))
        configure(home)
        from starlette.testclient import TestClient

        from app.gateway.app import create_app
        from app.gateway.evaluations.corpus import seed_corpus

        with TestClient(create_app()) as client:
            response = client.post("/api/v1/auth/register", json={"email": "agent-evaluation@example.com", "password": secrets.token_urlsafe(24)})
            _require(response)
            csrf = client.cookies.get("csrf_token")
            if not csrf:
                raise RuntimeError("Gateway registration did not establish a CSRF session")
            client.headers["X-CSRF-Token"] = csrf
            release = client.portal.call(seed_corpus)
            write_json(directory / "environment.json", release)
            for case in cases:
                if (directory / "cancel").exists():
                    break
                write_json(directory / f"{case.id}.json", execute_case(client, case, release, directory))
        write_json(directory / "finished.json", {"completed": True})
        return 0
    except Exception as exc:
        write_json(directory / "setup-error.json", {"error": f"{type(exc).__name__}: {exc}"})
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
