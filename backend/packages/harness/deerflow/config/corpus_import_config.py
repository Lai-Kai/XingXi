from __future__ import annotations

from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CorpusRootConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    path: Path


class CorpusImportConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    roots: tuple[CorpusRootConfig, ...] = ()

    @model_validator(mode="after")
    def validate_unique_roots(self) -> CorpusImportConfig:
        ids = [root.id for root in self.roots]
        if len(ids) != len(set(ids)):
            raise ValueError("corpus_import root IDs must be unique")
        return self

    def resolve_storage_uri(self, storage_uri: str) -> Path:
        parsed = urlsplit(storage_uri)
        if parsed.scheme != "corpus" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("invalid corpus storage URI")
        root = next((root for root in self.roots if root.id == parsed.netloc), None)
        if root is None:
            raise ValueError("corpus storage URI uses an unallowlisted root")
        relative_value = unquote(parsed.path).lstrip("/")
        relative = PurePosixPath(relative_value)
        if not relative_value or relative.is_absolute() or "\\" in relative_value or ".." in relative.parts:
            raise ValueError("unsafe corpus storage URI path")
        root_path = root.path.resolve()
        candidate = root_path.joinpath(*relative.parts)
        current = root_path
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("corpus storage URI resolves through a symbolic link")
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root_path)
        except ValueError as exc:
            raise ValueError("corpus storage URI escapes its allowlisted root") from exc
        return resolved
