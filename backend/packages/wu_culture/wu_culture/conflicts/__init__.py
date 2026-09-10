"""Multi-source conflict detection for historical evidence packs."""

from __future__ import annotations

from .models import (
    ClaimVariant,
    ConflictReport,
    ConflictType,
    UncertaintyLevel,
)
from .service import detect_conflicts

__all__ = [
    "ClaimVariant",
    "ConflictReport",
    "ConflictType",
    "UncertaintyLevel",
    "detect_conflicts",
]
