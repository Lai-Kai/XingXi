from __future__ import annotations

import hashlib
import re


def calculate_bundle_id(corpus_root_id: str, relative_directory: str) -> str:
    return hashlib.sha256(f"{corpus_root_id}\0{relative_directory}".encode()).hexdigest()


def is_safe_relative_directory(value: str) -> bool:
    if not value or value.startswith("/") or "\\" in value or "\0" in value or re.match(r"^[A-Za-z]:", value):
        return False
    parts = value.split("/")
    return all(part not in {"", ".", ".."} for part in parts)
