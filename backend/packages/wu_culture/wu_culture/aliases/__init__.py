"""Alias query expansion and admin merge review."""

from .authority import (
    AuthorityDecision,
    AuthorityEvidence,
    EvidenceLookup,
    NameAuthorityCandidate,
    NameAuthorityRequest,
    NameAuthorityResolution,
    NameAuthorityService,
    NameVariantInput,
)
from .review import (
    AliasMergeProposal,
    AliasMergeStatus,
    AliasReviewService,
    AliasSuggestion,
)
from .service import (
    AliasExpansionCandidate,
    AliasExpansionRequest,
    AliasExpansionResult,
    AliasExpansionService,
    AliasIndexError,
    AliasRecord,
    AliasRepository,
    AliasType,
    AsyncAliasExpansionService,
    AsyncAliasRepository,
    InMemoryAliasRepository,
    expand_alias_records,
)

__all__ = [
    "AuthorityDecision",
    "AuthorityEvidence",
    "AliasExpansionCandidate",
    "AliasExpansionRequest",
    "AliasExpansionResult",
    "AliasExpansionService",
    "AliasIndexError",
    "AliasMergeProposal",
    "AliasMergeStatus",
    "AliasRecord",
    "AliasRepository",
    "AliasReviewService",
    "AliasSuggestion",
    "AliasType",
    "AsyncAliasExpansionService",
    "AsyncAliasRepository",
    "InMemoryAliasRepository",
    "EvidenceLookup",
    "NameAuthorityCandidate",
    "NameAuthorityRequest",
    "NameAuthorityResolution",
    "NameAuthorityService",
    "NameVariantInput",
    "expand_alias_records",
]
