from __future__ import annotations

import pytest
from wu_culture.aliases import AliasMergeStatus, AliasReviewService, AliasType
from wu_culture.models import EntityType


def test_suggest_and_approve_alias_merge() -> None:
    service = AliasReviewService()
    suggestions = service.suggest_entities(
        "普济桥旧名",
        [("e1", "普济桥"), ("e2", "如意桥"), ("e3", "香溪")],
    )
    assert suggestions
    assert suggestions[0].entity_id in {"e1", "e2", "e3"}

    proposal = service.propose(
        entity_id="e1",
        canonical_name="普济桥",
        entity_type=EntityType.BRIDGE,
        alias="普济古桥",
        alias_type=AliasType.HISTORICAL_NAME,
        evidence_ids=("ev-1",),
    )
    assert proposal.status is AliasMergeStatus.CANDIDATE
    approved = service.approve(proposal.id, reviewer="admin")
    assert approved.status is AliasMergeStatus.APPROVED
    assert service.list_approved_records()[0].alias == "普济古桥"


def test_conflict_and_revoke() -> None:
    service = AliasReviewService()
    first = service.propose(
        entity_id="e1",
        canonical_name="普济桥",
        entity_type=EntityType.BRIDGE,
        alias="旧普济",
        alias_type=AliasType.HISTORICAL_NAME,
        evidence_ids=("ev-1",),
        auto_approve=True,
    )
    with pytest.raises(ValueError, match="alias conflict"):
        service.propose(
            entity_id="e2",
            canonical_name="如意桥",
            entity_type=EntityType.BRIDGE,
            alias="旧普济",
            alias_type=AliasType.HISTORICAL_NAME,
            evidence_ids=("ev-2",),
        )
    revoked = service.revoke(first.id, reviewer="admin", reason="错误归并")
    assert revoked.status is AliasMergeStatus.REVOKED
    assert service.list_approved_records() == ()


def test_no_evidence_alias_rejected() -> None:
    service = AliasReviewService()
    with pytest.raises(ValueError, match="evidence_ids"):
        service.propose(
            entity_id="e1",
            canonical_name="普济桥",
            entity_type=EntityType.BRIDGE,
            alias="俗称",
            alias_type=AliasType.COLLOQUIAL_NAME,
            evidence_ids=(),
        )


def test_normalized_duplicate_and_model_auto_approval_are_rejected() -> None:
    service = AliasReviewService()
    service.propose(
        entity_id="e1",
        canonical_name="木渎桥",
        entity_type=EntityType.BRIDGE,
        alias="古桥",
        alias_type=AliasType.HISTORICAL_NAME,
        evidence_ids=("ev-1",),
    )
    with pytest.raises(ValueError, match="already linked"):
        service.propose(
            entity_id="e1",
            canonical_name="木渎桥",
            entity_type=EntityType.BRIDGE,
            alias=" 古桥 ",
            alias_type=AliasType.HISTORICAL_NAME,
            evidence_ids=("ev-1",),
        )
    with pytest.raises(ValueError, match="cannot auto-approve"):
        service.propose(
            entity_id="e2",
            canonical_name="另一座桥",
            entity_type=EntityType.BRIDGE,
            alias="别名",
            alias_type=AliasType.HISTORICAL_NAME,
            evidence_ids=("ev-2",),
            submitted_by="model",
            auto_approve=True,
        )
