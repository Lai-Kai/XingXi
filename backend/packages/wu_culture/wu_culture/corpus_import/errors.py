from __future__ import annotations


class CorpusImportError(ValueError):
    def __init__(self, code: str, message: str, *, relative_path: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.relative_path = relative_path
