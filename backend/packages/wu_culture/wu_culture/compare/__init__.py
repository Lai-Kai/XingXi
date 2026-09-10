"""Multi-source source comparison (对读) for researchers."""

from __future__ import annotations

from .models import CompareSourcesRequest, CompareSourcesResult, SourceColumn
from .service import compare_sources

__all__ = [
    "CompareSourcesRequest",
    "CompareSourcesResult",
    "SourceColumn",
    "compare_sources",
]
