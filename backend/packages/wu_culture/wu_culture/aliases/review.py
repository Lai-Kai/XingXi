"""Admin-facing alias merge, conflict and revoke workflow."""

from __future__ import annotations

import unicodedata
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from rapidfuzz import fuzz, process

from wu_culture.aliases.service import AliasRecord, AliasType
from wu_culture.filters import Dynasty
from wu_culture.models import EntityType, ReviewStatus


class AliasMergeStatus(StrEnum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class AliasMergeProposal(_Model):
    id: str = Field(min_length=1, max_length=255)
    entity_id: str = Field(min_length=1, max_length=255)
    canonical_name: str = Field(min_length=1, max_length=255)
    entity_type: EntityType
    alias: str = Field(min_length=1, max_length=255)
    alias_type: AliasType
    applicable_dynasties: tuple[Dynasty, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    status: AliasMergeStatus = AliasMergeStatus.CANDIDATE
    submitted_by: str = "system"
    reason: str | None = None
    created_at: datetime
    decided_at: datetime | None = None


class AliasSuggestion(_Model):
    entity_id: str
    canonical_name: str
    score: float
    method: Literal["rapidfuzz"] = "rapidfuzz"


class AliasReviewService:
    """Rule + RapidFuzz assisted alias merge with mandatory human approval."""

    def __init__(self) -> None:
        self._proposals: dict[str, AliasMergeProposal] = {}
        self._approved: dict[str, AliasRecord] = {}

    def suggest_entities(
        self,
        alias: str,
        entities: list[tuple[str, str]],
        *,
        limit: int = 5,
        score_cutoff: float = 60,
    ) -> list[AliasSuggestion]:
        if not entities:
            return []
        choices = {entity_id: name for entity_id, name in entities}
        matches = process.extract(
            alias,
            choices,
            scorer=fuzz.WRatio,
            limit=limit,
            score_cutoff=score_cutoff,
        )
        # rapidfuzz returns (choice, score, key) when choices is a mapping
        suggestions: list[AliasSuggestion] = []
        for match in matches:
            if len(match) == 3:
                name, score, entity_id = match
            else:
                name, score = match[0], match[1]
                entity_id = next(eid for eid, n in entities if n == name)
            suggestions.append(
                AliasSuggestion(entity_id=str(entity_id), canonical_name=str(name), score=float(score))
            )
        return suggestions

    def propose(
        self,
        *,
        entity_id: str,
        canonical_name: str,
        entity_type: EntityType,
        alias: str,
        alias_type: AliasType,
        evidence_ids: tuple[str, ...] = (),
        applicable_dynasties: tuple[Dynasty, ...] = (),
        submitted_by: str = "admin",
        auto_approve: bool = False,
    ) -> AliasMergeProposal:
        if submitted_by.strip().lower() in {"model", "agent", "assistant"} and auto_approve:
            raise ValueError("model cannot auto-approve alias merges")
        normalized_alias = _normalize(alias)
        normalized_canonical = _normalize(canonical_name)
        if not evidence_ids:
            raise ValueError("alias merge requires evidence_ids")
        if len(evidence_ids) != len(set(evidence_ids)) or any(not item.strip() for item in evidence_ids):
            raise ValueError("alias evidence IDs must be unique and non-empty")
        if normalized_alias == normalized_canonical:
            raise ValueError("alias must differ from canonical_name")
        # Check candidates and approved records so duplicate submissions cannot
        # race a later approval or create duplicate index rows.
        active = (
            proposal
            for proposal in self._proposals.values()
            if proposal.status in {AliasMergeStatus.CANDIDATE, AliasMergeStatus.APPROVED}
        )
        for record in active:
            if _normalize(record.alias) == normalized_alias:
                if record.entity_id == entity_id:
                    raise ValueError(f"alias already linked to entity {entity_id}")
                raise ValueError(
                    f"alias conflict: '{alias}' already linked to entity {record.entity_id}"
                )
        proposal = AliasMergeProposal(
            id=f"alias-merge-{uuid.uuid4().hex[:10]}",
            entity_id=entity_id,
            canonical_name=canonical_name,
            entity_type=entity_type,
            alias=alias,
            alias_type=alias_type,
            applicable_dynasties=applicable_dynasties,
            evidence_ids=evidence_ids,
            status=AliasMergeStatus.CANDIDATE,
            submitted_by=submitted_by,
            created_at=datetime.now(UTC),
        )
        self._proposals[proposal.id] = proposal
        if auto_approve:
            return self.approve(proposal.id, reviewer="system")
        return proposal

    def approve(self, proposal_id: str, *, reviewer: str) -> AliasMergeProposal:
        proposal = self._require(proposal_id)
        if proposal.status not in {AliasMergeStatus.CANDIDATE, AliasMergeStatus.REVOKED}:
            raise ValueError(f"cannot approve proposal in status {proposal.status}")
        decided = proposal.model_copy(
            update={
                "status": AliasMergeStatus.APPROVED,
                "decided_at": datetime.now(UTC),
                "reason": f"approved_by={reviewer}",
            }
        )
        self._proposals[proposal_id] = decided
        self._approved[proposal_id] = AliasRecord(
            id=proposal_id,
            release_id="pending-release",
            entity_id=decided.entity_id,
            canonical_name=decided.canonical_name,
            entity_type=decided.entity_type,
            alias=decided.alias,
            alias_type=decided.alias_type,
            applicable_dynasties=decided.applicable_dynasties,
            evidence_ids=decided.evidence_ids,
            review_status=ReviewStatus.REVIEWED,
            indexed_at=datetime.now(UTC),
        )
        return decided

    def reject(self, proposal_id: str, *, reviewer: str, reason: str) -> AliasMergeProposal:
        proposal = self._require(proposal_id)
        decided = proposal.model_copy(
            update={
                "status": AliasMergeStatus.REJECTED,
                "decided_at": datetime.now(UTC),
                "reason": f"rejected_by={reviewer};{reason}",
            }
        )
        self._proposals[proposal_id] = decided
        self._approved.pop(proposal_id, None)
        return decided

    def revoke(self, proposal_id: str, *, reviewer: str, reason: str) -> AliasMergeProposal:
        proposal = self._require(proposal_id)
        if proposal.status is not AliasMergeStatus.APPROVED:
            raise ValueError("only approved merges can be revoked")
        decided = proposal.model_copy(
            update={
                "status": AliasMergeStatus.REVOKED,
                "decided_at": datetime.now(UTC),
                "reason": f"revoked_by={reviewer};{reason}",
            }
        )
        self._proposals[proposal_id] = decided
        self._approved.pop(proposal_id, None)
        return decided

    def list_approved_records(self) -> tuple[AliasRecord, ...]:
        return tuple(self._approved.values())

    def list_proposals(
        self, *, status: AliasMergeStatus | None = None
    ) -> tuple[AliasMergeProposal, ...]:
        proposals = tuple(self._proposals.values())
        if status is not None:
            proposals = tuple(item for item in proposals if item.status is status)
        return tuple(sorted(proposals, key=lambda item: (item.created_at, item.id)))

    def get(self, proposal_id: str) -> AliasMergeProposal | None:
        return self._proposals.get(proposal_id)

    def _require(self, proposal_id: str) -> AliasMergeProposal:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise KeyError(proposal_id)
        return proposal


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()
