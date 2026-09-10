from __future__ import annotations

import math
import unicodedata
from functools import lru_cache
from typing import Literal

try:
    import tiktoken
except ImportError:  # pragma: no cover - harness declares the dependency
    tiktoken = None


def estimate_text_tokens(text: str) -> int:
    """Conservatively estimate mixed CJK/Latin text without network access."""
    if not text:
        return 0
    cjk = sum(1 for char in text if unicodedata.east_asian_width(char) in {"W", "F"})
    return cjk + math.ceil((len(text) - cjk) / 4)


@lru_cache(maxsize=4)
def _encoding(name: str):  # noqa: ANN202
    if tiktoken is None:
        return None
    try:
        return tiktoken.get_encoding(name)
    except Exception:
        return None


def count_text_tokens(
    text: str,
    *,
    strategy: Literal["tiktoken", "char"] = "char",
    encoding_name: str = "cl100k_base",
) -> int:
    """Count prompt tokens, falling back to a conservative CJK estimate."""
    if strategy == "tiktoken":
        encoding = _encoding(encoding_name)
        if encoding is not None:
            try:
                return len(encoding.encode(text))
            except Exception:
                pass
    return estimate_text_tokens(text)
