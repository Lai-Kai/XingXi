from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from wu_culture.modes import resolve_mode_profile


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    description: str
    admin_only: bool = False
    modes: tuple[str, ...] = ("flash", "pro", "ultra")


_TOOLS = (
    ToolSpec(name="search_sources", description="Retrieve evidence pack for a query"),
    ToolSpec(name="query_knowledge_graph", description="Query bounded entity relationships"),
    ToolSpec(name="query_timeline", description="Query historical events"),
    ToolSpec(name="query_map_features", description="Query evidence-aware map locations"),
    ToolSpec(name="gloss_ancient_text", description="Gloss classical Chinese while preserving the original"),
    ToolSpec(name="resolve_name_variants", description="Adjudicate historical name variants from reviewed evidence"),
    ToolSpec(name="compare_sources", description="Side-by-side multi-source comparison", modes=("pro", "ultra")),
    ToolSpec(name="publish_release", description="Publish knowledge release", admin_only=True, modes=()),
)


def list_public_tools(mode: str | None = None) -> list[ToolSpec]:
    profile = resolve_mode_profile(mode)
    allowed = []
    for tool in _TOOLS:
        if tool.admin_only:
            continue
        if profile.mode.value not in tool.modes and tool.modes:
            continue
        allowed.append(tool)
    return allowed
