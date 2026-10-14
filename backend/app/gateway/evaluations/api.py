"""Governance reads and admin-only replay execution; no arbitrary code input."""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.gateway.deps import require_admin_user, require_business_capability
from app.gateway.evaluations.reports import export_report
from app.gateway.evaluations.service import environment_snapshot
from app.gateway.evaluations.suites import SUITE_VERSION, EvaluationCase, load_suite, select_cases
from deerflow.persistence.engine import get_session_factory
from deerflow.persistence.operations.evaluations import EvaluationRepository

router = APIRouter(prefix="/api/operations/evaluations", tags=["operations"])


def repository() -> EvaluationRepository:
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(503, "Automatic evaluations require a SQL database")
    return EvaluationRepository(sf)


async def reader(request: Request):
    return await require_business_capability(request, "governance:read", detail="Governance privileges are required")


async def writer(request: Request):
    user = await reader(request)
    await require_admin_user(request, detail="Only administrators may execute or review agent evaluations")
    return user


class ExecutionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=8, max_length=128)
    case_ids: tuple[str, ...] = Field(default=(), max_length=100)
    smoke: bool = True


class RerunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=8, max_length=128)
    failed_only: bool = True


class ReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    case_id: str = Field(min_length=1, max_length=128)
    decision: Literal["confirmed", "disagreed", "needs_review"]
    note: str = Field(min_length=1, max_length=4000)


async def _get(repo, run_id):
    batch = await repo.get(run_id)
    if batch is None:
        raise HTTPException(404, "Evaluation not found")
    return batch


def _require_worker(request):
    if getattr(request.app.state, "evaluation_service", None) is None:
        raise HTTPException(503, "Evaluation worker is unavailable")


@router.get("/catalog")
async def catalog(request: Request):
    await reader(request)
    return {"version": SUITE_VERSION, "execution_mode": "replay", "available": getattr(request.app.state, "evaluation_service", None) is not None, "cases": [case.model_dump(mode="json") for case in load_suite()]}


@router.get("/executions")
async def list_executions(request: Request, limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0), repo: EvaluationRepository = Depends(repository)):
    await reader(request)
    return await repo.list(limit=limit, offset=offset)


@router.post("/executions", status_code=202)
async def create_execution(body: ExecutionCreate, request: Request, repo: EvaluationRepository = Depends(repository)):
    user = await writer(request)
    _require_worker(request)
    try:
        cases = select_cases(body.case_ids, smoke=body.smoke)
        environment = await asyncio.to_thread(environment_snapshot)
        return await repo.create(actor_id=str(user.id), request_key=body.request_key, cases=[case.model_dump(mode="json") for case in cases], environment=environment)
    except ValueError as exc:
        raise HTTPException(409 if "idempotency" in str(exc) else 422, str(exc)) from exc


@router.get("/executions/{run_id}")
async def get_execution(run_id: str, request: Request, repo: EvaluationRepository = Depends(repository)):
    await reader(request)
    return await _get(repo, run_id)


@router.post("/executions/{run_id}/cancel")
async def cancel_execution(run_id: str, request: Request, repo: EvaluationRepository = Depends(repository)):
    await writer(request)
    await _get(repo, run_id)
    await repo.cancel(run_id)
    return await repo.get(run_id)


@router.post("/executions/{run_id}/rerun", status_code=202)
async def rerun_execution(run_id: str, body: RerunCreate, request: Request, repo: EvaluationRepository = Depends(repository)):
    user = await writer(request)
    _require_worker(request)
    original = await _get(repo, run_id)
    if original["status"] in {"queued", "running"}:
        raise HTTPException(409, "Wait for the original evaluation to finish")
    selected = {result["case_id"] for result in original["results"] if not body.failed_only or result.get("verdict") != "passed"}
    cases = [EvaluationCase.model_validate(case).model_dump(mode="json") for case in original["spec"]["cases"] if case["id"] in selected]
    if not cases:
        raise HTTPException(422, "No matching cases to rerun")
    try:
        return await repo.create(actor_id=str(user.id), request_key=body.request_key, cases=cases, environment=await asyncio.to_thread(environment_snapshot), parent_id=run_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/executions/{run_id}/reviews", status_code=201)
async def add_review(run_id: str, body: ReviewCreate, request: Request, repo: EvaluationRepository = Depends(repository)):
    user = await writer(request)
    await _get(repo, run_id)
    try:
        await repo.add_review(run_id, actor_id=str(user.id), **body.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return await repo.get(run_id)


@router.get("/executions/{run_id}/export")
async def export_execution(run_id: str, request: Request, format: Literal["json", "csv", "markdown", "html"] = "markdown", repo: EvaluationRepository = Depends(repository)):
    await reader(request)
    batch = await _get(repo, run_id)
    extension, mime = {"json": ("json", "application/json"), "csv": ("csv", "text/csv"), "markdown": ("md", "text/markdown"), "html": ("html", "text/html")}[format]
    content = await asyncio.to_thread(export_report, batch, format)
    return Response(
        content,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="evaluation-{batch["id"]}.{extension}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
        },
    )
