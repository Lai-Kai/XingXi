from __future__ import annotations

import re
from collections.abc import Iterable

from pydantic import ValidationError

from .errors import CorpusImportError
from .identity import calculate_bundle_id, is_safe_relative_directory
from .models import CorpusBundleManifest

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def validate_manifest(lines: Iterable[str]) -> tuple[CorpusBundleManifest, ...]:
    entries: list[CorpusBundleManifest] = []
    bundle_ids: set[str] = set()
    relative_directories: set[tuple[str, str]] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            entry = CorpusBundleManifest.model_validate_json(line)
        except ValidationError as exc:
            raise CorpusImportError("invalid_manifest", f"Manifest line {line_number} is invalid") from exc
        declared_assets = set(entry.assets.model_dump().values())
        if set(entry.hashes) != declared_assets or set(entry.sizes) != declared_assets:
            raise CorpusImportError("asset_manifest_mismatch", f"Manifest line {line_number} must include one hash and size for every declared asset")
        if any(_SHA256.fullmatch(value) is None for value in entry.hashes.values()) or any(value < 0 for value in entry.sizes.values()):
            raise CorpusImportError("invalid_asset_metadata", f"Manifest line {line_number} contains an invalid asset hash or size")
        if not is_safe_relative_directory(entry.relative_directory):
            raise CorpusImportError("unsafe_relative_path", f"Manifest line {line_number} contains an unsafe relative directory")
        if entry.bundle_id != calculate_bundle_id(entry.corpus_root_id, entry.relative_directory):
            raise CorpusImportError("bundle_identity_mismatch", f"Manifest line {line_number} has a bundle ID that does not match its relative path")
        relative_identity = (entry.corpus_root_id, entry.relative_directory)
        if entry.bundle_id in bundle_ids or relative_identity in relative_directories:
            raise CorpusImportError("duplicate_manifest_entry", f"Manifest line {line_number} duplicates a bundle identity")
        bundle_ids.add(entry.bundle_id)
        relative_directories.add(relative_identity)
        entries.append(entry)
    if not entries:
        raise CorpusImportError("empty_manifest", "Manifest contains no entries")
    return tuple(entries)
