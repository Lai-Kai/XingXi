from __future__ import annotations

from types import SimpleNamespace

from deerflow.agents.xingxi.tools import (
    _project_document_ids_from_runtime,
    _project_scoped_document_ids,
)


def test_project_scope_defaults_to_all_project_documents() -> None:
    runtime = SimpleNamespace(
        context={"research_project_document_ids": ["document-1", "document-2"]}
    )

    assert _project_document_ids_from_runtime(runtime) == ["document-1", "document-2"]
    assert _project_scoped_document_ids(runtime, None) == ["document-1", "document-2"]


def test_project_scope_intersects_model_requested_documents() -> None:
    runtime = SimpleNamespace(
        context={"research_project_document_ids": ["document-1", "document-2"]}
    )

    assert _project_scoped_document_ids(
        runtime,
        ["document-outside", "document-2"],
    ) == ["document-2"]
    assert _project_scoped_document_ids(runtime, ["document-outside"]) == []


def test_search_without_project_keeps_requested_documents() -> None:
    runtime = SimpleNamespace(context={})

    assert _project_document_ids_from_runtime(runtime) is None
    assert _project_scoped_document_ids(runtime, ["document-3"]) == ["document-3"]
