from __future__ import annotations

import pytest
from pydantic import ValidationError

from deerflow.config.corpus_import_config import CorpusImportConfig, CorpusRootConfig


def test_corpus_import_config_resolves_allowlisted_storage_uri(tmp_path):
    root = tmp_path / "fuxianzhi"
    config = CorpusImportConfig(roots=(CorpusRootConfig(id="fuxianzhi", path=root),))

    resolved = config.resolve_storage_uri("corpus://fuxianzhi/苏州/府志/book.pdf")

    assert resolved == root.resolve() / "苏州" / "府志" / "book.pdf"


@pytest.mark.parametrize(
    "uri",
    (
        "corpus://unknown/苏州/book.pdf",
        "corpus://fuxianzhi/../outside.pdf",
        "corpus://fuxianzhi/苏州\\outside.pdf",
        "file:///data/corpora/fuxianzhi/book.pdf",
    ),
)
def test_corpus_import_config_rejects_unallowlisted_or_unsafe_uri(tmp_path, uri):
    config = CorpusImportConfig(roots=(CorpusRootConfig(id="fuxianzhi", path=tmp_path),))

    with pytest.raises(ValueError):
        config.resolve_storage_uri(uri)


def test_corpus_import_config_rejects_duplicate_root_ids(tmp_path):
    with pytest.raises(ValidationError):
        CorpusImportConfig(
            roots=(
                CorpusRootConfig(id="fuxianzhi", path=tmp_path / "one"),
                CorpusRootConfig(id="fuxianzhi", path=tmp_path / "two"),
            )
        )
