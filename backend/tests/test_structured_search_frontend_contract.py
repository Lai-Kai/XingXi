from __future__ import annotations

import re
from pathlib import Path

from wu_culture import EntityType, ReviewStatus, SourceLevel, SourceType
from wu_culture.filters import Dynasty, StructuredSearchFilters

FRONTEND_TYPES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "core" / "knowledge-search" / "types.ts"


def test_frontend_structured_filter_contract_matches_backend_schema() -> None:
    source = FRONTEND_TYPES.read_text(encoding="utf-8")
    quoted_values = set(re.findall(r'"([a-zA-Z0-9_]+)"', source))

    expected_enums = {
        *(value.value for value in Dynasty),
        *(value.value for value in EntityType),
        *(value.value for value in SourceType),
        *(value.value for value in SourceLevel),
        *(value.value for value in ReviewStatus),
    }
    assert expected_enums <= quoted_values
    filter_block = re.search(r"export interface StructuredSearchFilters \{(?P<body>.*?)\n\}", source, flags=re.DOTALL)
    assert filter_block is not None
    assert set(StructuredSearchFilters.model_fields) == set(re.findall(r"^  ([a-z_]+)\?:", filter_block.group("body"), flags=re.MULTILINE))
