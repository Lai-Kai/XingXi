"""Stage 80: controlled public knowledge API surface.

Only exposes read-only, authorization-aware endpoints. Does not open admin
ingestion, release publishing, or agent runtime control.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from wu_culture import AuthorizedUse
from wu_culture.citations.contract import evidence_detail_from_record
from wu_culture.citations.models import EvidenceDetail

from deerflow.persistence.engine import get_session_factory

router = APIRouter(prefix="/api/public/knowledge", tags=["public-knowledge"])


class PublicSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=500)
    release_id: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


@router.get("/health")
async def public_knowledge_health() -> dict[str, str]:
    return {"status": "ok", "surface": "public-knowledge", "mode": "controlled"}


@router.get("/evidence/{evidence_id}", response_model=EvidenceDetail)
async def public_get_evidence(
    evidence_id: str,
    use: AuthorizedUse = Query(default=AuthorizedUse.PUBLIC_QUOTE),
) -> EvidenceDetail:
    """Read-only evidence locator for public quote use."""
    # This endpoint is intentionally anonymous. Authorization is enforced by
    # the source-use policy below, while admin mutations remain on private
    # routers protected by the gateway auth middleware.
    if use not in {AuthorizedUse.PUBLIC_QUOTE, AuthorizedUse.PUBLIC_FULL_TEXT}:
        raise HTTPException(status_code=403, detail="Public API only allows public quote/full-text uses")
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Public evidence lookup requires SQL database")
    from deerflow.persistence.wu_culture import SqlEvidenceRepository

    record = await SqlEvidenceRepository(session_factory).get_evidence(evidence_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    try:
        from wu_culture import evaluate_source_access
        decision = evaluate_source_access(record.document, use=use)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Source authorization policy unavailable") from exc
    if not decision.allowed:
        raise HTTPException(status_code=403, detail="Source not authorized for requested use")
    return evidence_detail_from_record(record)
