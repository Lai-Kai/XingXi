from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from .importer import build_import_bundle, plan_import, select_manifest_bundles
from .manifest import validate_manifest
from .scanner import scan_corpus


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m wu_culture.corpus_import.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="Scan a read-only fuxianzhi corpus and write a candidate JSONL manifest")
    scan.add_argument("--root", required=True, type=Path)
    scan.add_argument("--root-id", default="fuxianzhi")
    scan.add_argument("--output", required=True, type=Path)
    validate = commands.add_parser("validate", help="Validate a fuxianzhi JSONL manifest")
    validate.add_argument("--manifest", required=True, type=Path)
    import_command = commands.add_parser("import", help="Dry-run or commit precomputed fuxianzhi text")
    import_command.add_argument("--manifest", required=True, type=Path)
    import_command.add_argument("--root", required=True, type=Path)
    import_command.add_argument("--bundle")
    import_command.add_argument("--dry-run", action="store_true")
    import_command.add_argument(
        "--allow-unconfirmed-internal",
        action="store_true",
        help="Import unrated sources as an internal-only working corpus",
    )
    import_command.add_argument(
        "--publish-working-release",
        action="store_true",
        help="Create or reuse and activate an indexed internal working release",
    )
    import_command.add_argument("--actor", default="corpus-import-cli")
    import_command.add_argument("--max-characters", type=int, default=1000)
    import_command.add_argument("--overlap-characters", type=int, default=100)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "scan":
        result = scan_corpus(args.root, corpus_root_id=args.root_id)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        content = "".join(f"{bundle.model_dump_json()}\n" for bundle in result.bundles)
        args.output.write_text(content, encoding="utf-8", newline="\n")
        print(f"Scanned {result.bundle_count} bundles, {result.file_count} files, {result.page_count} pages")
        return 0
    if args.command == "validate":
        with args.manifest.open("r", encoding="utf-8-sig", errors="strict") as stream:
            entries = validate_manifest(stream)
        print(f"Validated {len(entries)} manifest entries")
        return 0
    if args.command == "import":
        manifest_bytes = args.manifest.read_bytes()
        entries = validate_manifest(manifest_bytes.decode("utf-8-sig").splitlines())
        report = plan_import(args.root, entries, bundle_selector=args.bundle)
        if args.dry_run:
            print(report.model_dump_json(indent=2))
            return 0
        if args.publish_working_release and not args.allow_unconfirmed_internal:
            raise ValueError("--publish-working-release requires --allow-unconfirmed-internal")
        if not report.can_commit and not args.allow_unconfirmed_internal:
            raise ValueError(f"Corpus import governance blockers: {', '.join(report.blockers)}")
        return asyncio.run(
            _commit_import(
                root=args.root,
                entries=entries,
                bundle_selector=args.bundle,
                manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                actor_id=args.actor,
                max_characters=args.max_characters,
                overlap_characters=args.overlap_characters,
                allow_unconfirmed_internal=args.allow_unconfirmed_internal,
                publish_working_release=args.publish_working_release,
            )
        )
    raise AssertionError(f"Unhandled command: {args.command}")


async def _commit_import(
    *,
    root: Path,
    entries,
    bundle_selector: str | None,
    manifest_sha256: str,
    actor_id: str,
    max_characters: int,
    overlap_characters: int,
    allow_unconfirmed_internal: bool,
    publish_working_release: bool,
) -> int:
    from deerflow.config.app_config import get_app_config
    from deerflow.persistence import close_engine, get_session_factory
    from deerflow.persistence.engine import init_engine_from_config
    from deerflow.persistence.wu_culture import (
        SqlCorpusImportRepository,
        SqlFullTextRepository,
        SqlKnowledgeReleaseRepository,
    )
    from wu_culture.chunking import ChunkingPolicy
    from wu_culture.releases import ActivateReleaseRequest, PublishReleaseRequest

    now = datetime.now(UTC)
    batch_id = f"corpus-batch-{manifest_sha256}"
    policy = ChunkingPolicy(
        split_version="fuxianzhi-v1",
        max_characters=max_characters,
        overlap_characters=overlap_characters,
    )
    await init_engine_from_config(get_app_config().database)
    session_factory = get_session_factory()
    if session_factory is None:
        raise RuntimeError("Corpus import requires a SQL database")
    repository = SqlCorpusImportRepository(session_factory)
    imported_count = 0
    reused_count = 0
    chunk_set_ids: list[str] = []
    try:
        selected_entries = select_manifest_bundles(entries, bundle_selector)
        completed_items = {
            item["bundle_id"]: item
            for item in await repository.list_items(batch_id)
            if item["status"] == "completed"
        }
        for ordinal, entry in enumerate(selected_entries, start=1):
            completed_item = completed_items.get(entry.bundle_id)
            if completed_item is not None:
                chunk_set_ids.append(completed_item["chunk_set_id"])
                reused_count += 1
                print(
                    json.dumps(
                        {
                            "progress": f"{ordinal}/{len(selected_entries)}",
                            "bundle_id": entry.bundle_id,
                            "title": entry.title,
                            "status": "reused",
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                continue
            artifact = build_import_bundle(
                root,
                entry,
                actor_id=actor_id,
                generated_at=now,
                chunking_policy=policy,
                allow_unconfirmed_internal=allow_unconfirmed_internal,
            )
            chunk_set_ids.append(artifact.chunk_set.id)
            result = await repository.import_bundle(
                batch_id=batch_id,
                manifest_sha256=manifest_sha256,
                corpus_root_id=entry.corpus_root_id,
                bundle_id=entry.bundle_id,
                imported=artifact,
                actor_id=actor_id,
                imported_at=now,
            )
            imported_count += int(result.imported)
            reused_count += int(not result.imported)
            print(
                json.dumps(
                    {
                        "progress": f"{ordinal}/{len(selected_entries)}",
                        "bundle_id": entry.bundle_id,
                        "title": entry.title,
                        "status": "imported" if result.imported else "reused",
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        await repository.complete_batch(batch_id, completed_at=datetime.now(UTC))
        release_id = None
        if publish_working_release:
            fulltext = SqlFullTextRepository(session_factory)
            releases = SqlKnowledgeReleaseRepository(session_factory, publication_indexer=fulltext)
            requested = set(chunk_set_ids)
            existing = next(
                (release for release in await releases.list_releases() if release.scope == "internal" and {item.chunk_set_id for item in release.items} == requested),
                None,
            )
            state = await releases.get_state()
            if existing is None:
                existing = await releases.publish(
                    PublishReleaseRequest(
                        chunk_set_ids=tuple(chunk_set_ids),
                        release_notes="府县志全量内部工作版本；内容与来源等级待人工复核，不可公开引用",
                        expected_state_version=state.state_version,
                        scope="internal",
                    ),
                    actor_id=actor_id,
                    created_at=datetime.now(UTC),
                )
            elif state.active_release_id != existing.id:
                await releases.activate(
                    ActivateReleaseRequest(
                        release_id=existing.id,
                        expected_state_version=state.state_version,
                        reason="Activate the complete internal fuxianzhi working corpus",
                    ),
                    actor_id=actor_id,
                    changed_at=datetime.now(UTC),
                )
            release_id = existing.id
    finally:
        await close_engine()
    print(
        json.dumps(
            {
                "batch_id": batch_id,
                "imported": imported_count,
                "reused": reused_count,
                "working_release_id": release_id,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
