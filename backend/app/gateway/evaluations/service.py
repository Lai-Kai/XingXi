"""Durable single-budget orchestration of isolated replay processes."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import subprocess
import sys
import time
import uuid
from pathlib import Path

from app.gateway.evaluations.reports import write_report
from app.gateway.evaluations.suites import DATASET_VERSION, SOURCE_TEXT, SUITE_VERSION, canonical_hash
from deerflow.persistence.operations.evaluations import EvaluationRepository

logger = logging.getLogger(__name__)
BACKEND = Path(__file__).resolve().parents[3]


def environment_snapshot() -> dict:
    from deerflow.agents.xingxi.prompt import XINGXI_SYSTEM_PROMPT

    def git(*args):
        try:
            result = subprocess.run(["git", *args], cwd=BACKEND, capture_output=True, timeout=5, check=False)
            return result.stdout if result.returncode == 0 else b""
        except (OSError, subprocess.TimeoutExpired):
            return b""

    sources = {str(path.relative_to(BACKEND)): path.read_text() for path in sorted(Path(__file__).parent.glob("*.py"))}
    return {
        "suite_version": SUITE_VERSION,
        "dataset_version": DATASET_VERSION,
        "evaluation_source_sha256": canonical_hash(sources),
        "dataset_sha256": canonical_hash(SOURCE_TEXT),
        "git_sha": git("rev-parse", "HEAD").decode().strip() or None,
        "working_diff_sha256": canonical_hash(git("diff", "--binary", "HEAD").hex()),
        "system_prompt_sha256": canonical_hash(XINGXI_SYSTEM_PROMPT),
        "python": platform.python_version(),
        "execution_mode": "replay",
        "model": "xingxi-synthetic-replay-v1",
        "grader_version": "deterministic-v1",
        "isolation": "fresh SQLite, memory disabled, no external model or tracing",
        "limitations": ["Synthetic scripted responses do not measure real-model decision quality.", "Only recorded event times are available; precise tool duration is not fabricated."],
    }


class EvaluationService:
    def __init__(self, repository: EvaluationRepository, root: Path):
        self.repository = repository
        self.root = root
        self.owner = uuid.uuid4().hex
        self.task: asyncio.Task | None = None

    def start(self) -> None:
        self.task = asyncio.create_task(self.run_forever(), name="xingxi-agent-evaluations")

    async def close(self) -> None:
        if self.task:
            self.task.cancel()
            try:
                await asyncio.wait_for(self.task, timeout=8)
            except (asyncio.CancelledError, TimeoutError):
                pass

    async def run_forever(self) -> None:
        while True:
            try:
                batch = await self.repository.claim(owner=self.owner)
                if batch:
                    await self.execute(batch)
                else:
                    await asyncio.sleep(2)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Agent evaluation worker failed")
                await asyncio.sleep(5)

    async def execute(self, batch: dict) -> None:
        directory = self.root / batch["id"]
        process = None
        log = None
        error = None
        received: set[str] = set()
        try:
            await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
            spec_path = directory / "spec.json"
            await asyncio.to_thread(spec_path.write_text, json.dumps(batch["spec"], ensure_ascii=False), encoding="utf-8")
            output = directory / "observations"
            await asyncio.to_thread(output.mkdir, exist_ok=True)
            # Inherit only runtime paths/locale, never model/provider credentials.
            environment = {key: value for key, value in os.environ.items() if key in {"PATH", "HOME", "SYSTEMROOT", "LANG", "LC_ALL", "TZ", "PYTHONPATH", "LD_LIBRARY_PATH"}}
            environment.update(PYTHON_DOTENV_DISABLED="1", XINGXI_EVALUATION_CHILD="1", PYTHONIOENCODING="utf-8")
            # Preserve deployment-provided Python instrumentation in its usual
            # order, then make application imports work from the isolated cwd.
            environment["PYTHONPATH"] = os.pathsep.join(path for path in (environment.get("PYTHONPATH", ""), str(BACKEND)) if path)
            log = await asyncio.to_thread((directory / "worker.log").open, "w", encoding="utf-8")
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "app.gateway.evaluations.runner", "--spec", str(spec_path), "--output", str(output), cwd=directory, env=environment, stdout=log, stderr=asyncio.subprocess.STDOUT
            )
            started = time.monotonic()
            cancelling_at = None
            while True:
                if not await self.repository.heartbeat(batch["id"], owner=self.owner):
                    raise RuntimeError("Evaluation worker lease was lost")
                current = await self.repository.get(batch["id"])
                if current["cancel_requested"]:
                    await asyncio.to_thread((output / "cancel").touch)
                    cancelling_at = cancelling_at or time.monotonic()
                for case in batch["spec"]["cases"]:
                    path = output / f"{case['id']}.json"
                    if case["id"] not in received and await asyncio.to_thread(path.is_file):
                        result = json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
                        await self.repository.record_result(batch["id"], case_id=case["id"], result=result, owner=self.owner)
                        received.add(case["id"])
                if process.returncode is not None:
                    if process.returncode:
                        path = output / "setup-error.json"
                        error = json.loads(await asyncio.to_thread(path.read_text)).get("error") if await asyncio.to_thread(path.is_file) else f"Evaluation process exited with code {process.returncode}"
                    break
                if time.monotonic() - started > 900:
                    raise TimeoutError("Evaluation batch exceeded its 15 minute budget")
                if cancelling_at and time.monotonic() - cancelling_at > 8:
                    error = "Evaluation process stopped after cancellation deadline"
                    break
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            error = "Gateway stopped during evaluation; rerun creates a new attempt"
            raise
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            logger.exception("Evaluation %s failed", batch["id"])
        finally:
            if process and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=3)
                except TimeoutError:
                    process.kill()
                    await process.wait()
            if log:
                log.close()
            try:
                # The child may finish its final atomic write just after the
                # polling scan. Collect once more after it has fully stopped.
                for case in batch["spec"]["cases"]:
                    path = directory / "observations" / f"{case['id']}.json"
                    if case["id"] not in received and await asyncio.to_thread(path.is_file):
                        result = json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
                        await self.repository.record_result(batch["id"], case_id=case["id"], result=result, owner=self.owner)
                metadata_path = directory / "observations/environment.json"
                if await asyncio.to_thread(metadata_path.is_file):
                    metadata = json.loads(await asyncio.to_thread(metadata_path.read_text, encoding="utf-8"))
                    await self.repository.record_environment(batch["id"], environment=metadata, owner=self.owner)
                await self.repository.finish(batch["id"], owner=self.owner, error=error)
                final = await self.repository.get(batch["id"])
                await asyncio.to_thread(write_report, final, directory)
            except ValueError:
                logger.warning("Evaluation %s is now owned by another worker; preserving its state", batch["id"])


async def start_evaluations(app) -> None:
    from deerflow.config.runtime_paths import runtime_home
    from deerflow.persistence.engine import get_session_factory

    if os.environ.get("XINGXI_EVALUATION_CHILD") == "1":
        return
    sf = get_session_factory()
    if sf is None:
        return
    service = EvaluationService(EvaluationRepository(sf), runtime_home() / "evaluations")
    app.state.evaluation_service = service
    service.start()


async def stop_evaluations(app) -> None:
    service = getattr(app.state, "evaluation_service", None)
    if service:
        await service.close()
