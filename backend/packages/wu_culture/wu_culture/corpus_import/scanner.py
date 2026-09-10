from __future__ import annotations

import hashlib
from pathlib import Path

from .errors import CorpusImportError
from .identity import calculate_bundle_id
from .models import CorpusBundleAssets, CorpusBundleManifest, CorpusScanResult
from .page_markers import parse_page_marker

_ASSETS = CorpusBundleAssets()
_REQUIRED_FILENAMES = tuple(_ASSETS.model_dump().values())


def scan_corpus(root: str | Path, *, corpus_root_id: str = "fuxianzhi") -> CorpusScanResult:
    root_path = Path(root)
    if not root_path.is_dir():
        raise CorpusImportError("corpus_root_not_found", "Corpus root does not exist or is not a directory")

    bundle_directories = {path.parent for path in root_path.rglob("*") if path.is_file() and path.name in _REQUIRED_FILENAMES}
    if not bundle_directories:
        raise CorpusImportError("no_bundles_found", "Corpus root contains no recognizable fuxianzhi bundles")
    bundles = tuple(
        sorted(
            (_scan_bundle(root_path, bundle_dir, corpus_root_id=corpus_root_id) for bundle_dir in bundle_directories),
            key=lambda item: item.relative_directory,
        )
    )
    return CorpusScanResult(
        corpus_root_id=corpus_root_id,
        bundle_count=len(bundles),
        file_count=sum(len(bundle.hashes) for bundle in bundles),
        page_count=sum(bundle.page_count for bundle in bundles),
        bundles=bundles,
    )


def _scan_bundle(root: Path, bundle_dir: Path, *, corpus_root_id: str) -> CorpusBundleManifest:
    relative_directory = bundle_dir.relative_to(root).as_posix()
    missing = [name for name in _REQUIRED_FILENAMES if not (bundle_dir / name).is_file()]
    if missing:
        raise CorpusImportError(
            "incomplete_bundle",
            f"Bundle is missing required files: {', '.join(missing)}",
            relative_path=relative_directory,
        )
    for name in _REQUIRED_FILENAMES:
        if (bundle_dir / name).is_symlink():
            raise CorpusImportError(
                "unsafe_symlink",
                "Corpus bundle assets must not be symbolic links",
                relative_path=f"{relative_directory}/{name}",
            )

    parts = Path(relative_directory).parts
    hashes = {name: _sha256_file(bundle_dir / name) for name in _REQUIRED_FILENAMES}
    sizes = {name: (bundle_dir / name).stat().st_size for name in _REQUIRED_FILENAMES}
    text_filenames = (
        _ASSETS.ocr_raw_simplified,
        _ASSETS.ocr_raw_traditional,
        _ASSETS.clean_simplified,
        _ASSETS.clean_traditional,
    )
    page_locators: dict[str, tuple[tuple[int, str], ...]] = {}
    for name in text_filenames:
        try:
            page_locators[name] = _read_page_locators(bundle_dir / name)
        except UnicodeDecodeError as exc:
            raise CorpusImportError(
                "invalid_utf8",
                "Corpus text assets must use valid UTF-8",
                relative_path=f"{relative_directory}/{name}",
            ) from exc
    page_counts = {name: len(locators) for name, locators in page_locators.items()}
    if len(set(page_counts.values())) != 1:
        raise CorpusImportError(
            "page_alignment_mismatch",
            "Text variants must contain the same number of page markers",
            relative_path=relative_directory,
        )
    if len(set(page_locators.values())) != 1:
        raise CorpusImportError(
            "page_locator_mismatch",
            "Text variants must contain the same physical page and folio locators",
            relative_path=relative_directory,
        )
    canonical_locators = page_locators[_ASSETS.clean_traditional]
    if tuple(page_number for page_number, _ in canonical_locators) != tuple(range(1, len(canonical_locators) + 1)):
        raise CorpusImportError(
            "page_sequence_invalid",
            "Physical page sequence must start at 1 and remain continuous",
            relative_path=relative_directory,
        )
    return CorpusBundleManifest(
        bundle_id=calculate_bundle_id(corpus_root_id, relative_directory),
        corpus_root_id=corpus_root_id,
        relative_directory=relative_directory,
        region=parts[0],
        title=parts[-1],
        assets=_ASSETS,
        page_count=page_counts[_ASSETS.clean_traditional],
        hashes=hashes,
        sizes=sizes,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _read_page_locators(path: Path) -> tuple[tuple[int, str], ...]:
    locators: list[tuple[int, str]] = []
    with path.open("r", encoding="utf-8-sig", errors="strict") as stream:
        for line in stream:
            marker = parse_page_marker(line.rstrip("\r\n"))
            if marker is not None:
                locators.append(marker)
    if not locators:
        raise CorpusImportError("page_markers_missing", "Clean traditional text contains no page markers", relative_path=path.name)
    return tuple(locators)
