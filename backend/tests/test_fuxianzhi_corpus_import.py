from __future__ import annotations

import json
from datetime import UTC, datetime
from io import StringIO

import pytest
from wu_culture.chunking import ChunkingPolicy
from wu_culture.corpus_import import (
    CorpusImportError,
    analyze_page_quality,
    build_import_bundle,
    calculate_bundle_id,
    load_bundle_pages,
    parse_paginated_texts,
    plan_import,
    scan_corpus,
    validate_manifest,
)
from wu_culture.corpus_import.cli import main
from wu_culture.ingestion import IngestionJobStatus, IngestionStepName, IngestionStepStatus


def _write_complete_bundle(bundle_dir, *, text_by_filename: dict[str, str] | None = None) -> None:
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "book.pdf").write_bytes(b"%PDF-1.4\nsynthetic fixture")
    default_text = "===== 第 1 页 (folio 1) =====\n正文"
    for name in (
        "text_raw_简体.txt",
        "text_raw_繁体.txt",
        "text_简体.txt",
        "text_繁体.txt",
    ):
        (bundle_dir / name).write_text((text_by_filename or {}).get(name, default_text), encoding="utf-8")
    for name in ("text_简体.html", "text_繁体.html"):
        (bundle_dir / name).write_text("<p>正文</p>", encoding="utf-8")


def test_scan_corpus_discovers_complete_bundle_with_safe_manifest_defaults(tmp_path):
    bundle_dir = tmp_path / "苏州" / "（同治）苏州府志"
    _write_complete_bundle(bundle_dir)

    result = scan_corpus(tmp_path)

    assert result.bundle_count == 1
    bundle = result.bundles[0]
    assert bundle.relative_directory == "苏州/（同治）苏州府志"
    assert bundle.region == "苏州"
    assert bundle.title == "（同治）苏州府志"
    assert bundle.assets.original_pdf == "book.pdf"
    assert bundle.page_count == 1
    assert bundle.authorization_status.value == "unconfirmed"
    assert bundle.visibility_scope.value == "internal"
    assert bundle.authorized_uses == ()


def test_parse_paginated_texts_aligns_raw_clean_and_simplified_by_page_and_folio():
    raw = """===== 第 1 页 (folio 1) =====
原始繁體第一頁
===== 第 2 页 (folio 3) =====
原始繁體第二頁
"""
    clean = """===== 第 1 页 (folio 1) =====
清理繁體第一頁
===== 第 2 页 (folio 3) =====
清理繁體第二頁
"""
    simplified = """===== 第 1 页 (folio 1) =====
清理简体第一页
===== 第 2 页 (folio 3) =====
清理简体第二页
"""

    pages = parse_paginated_texts(
        raw_traditional=StringIO(raw),
        clean_traditional=StringIO(clean),
        clean_simplified=StringIO(simplified),
    )

    assert [
        (
            page.physical_page_number,
            page.folio_label,
            page.raw_traditional,
            page.clean_traditional,
            page.clean_simplified,
        )
        for page in pages
    ] == [
        (1, "1", "原始繁體第一頁", "清理繁體第一頁", "清理简体第一页"),
        (2, "3", "原始繁體第二頁", "清理繁體第二頁", "清理简体第二页"),
    ]


def test_scan_corpus_rejects_incomplete_bundle_even_when_pdf_is_missing(tmp_path):
    bundle_dir = tmp_path / "太仓" / "（咸丰）壬癸志稿"
    bundle_dir.mkdir(parents=True)
    for name in (
        "text_raw_简体.txt",
        "text_raw_繁体.txt",
        "text_简体.txt",
        "text_繁体.txt",
        "text_简体.html",
        "text_繁体.html",
    ):
        (bundle_dir / name).write_text("fixture", encoding="utf-8")

    with pytest.raises(CorpusImportError) as caught:
        scan_corpus(tmp_path)

    assert caught.value.code == "incomplete_bundle"
    assert caught.value.relative_path == "太仓/（咸丰）壬癸志稿"
    assert "book.pdf" in caught.value.message


def test_scan_corpus_rejects_page_count_mismatch_between_text_variants(tmp_path):
    bundle_dir = tmp_path / "吴江" / "吴江县志"
    one_page = "===== 第 1 页 (folio 1) =====\n正文"
    two_pages = one_page + "\n===== 第 2 页 (folio 2) =====\n正文"
    _write_complete_bundle(bundle_dir, text_by_filename={"text_raw_繁体.txt": two_pages})

    with pytest.raises(CorpusImportError) as caught:
        scan_corpus(tmp_path)

    assert caught.value.code == "page_alignment_mismatch"
    assert caught.value.relative_path == "吴江/吴江县志"


def test_scan_cli_writes_jsonl_manifest_without_absolute_corpus_path(tmp_path):
    corpus_root = tmp_path / "corpus"
    _write_complete_bundle(corpus_root / "常熟" / "常熟县志")
    output = tmp_path / "manifests" / "fuxianzhi-v1.jsonl"

    exit_code = main(["scan", "--root", str(corpus_root), "--output", str(output)])

    assert exit_code == 0
    serialized = output.read_text(encoding="utf-8")
    payload = json.loads(serialized)
    assert payload["corpus_root_id"] == "fuxianzhi"
    assert payload["relative_directory"] == "常熟/常熟县志"
    assert str(corpus_root) not in serialized


def test_validate_cli_accepts_the_generated_jsonl_manifest(tmp_path, capsys):
    corpus_root = tmp_path / "corpus"
    _write_complete_bundle(corpus_root / "昆山" / "昆山县志")
    output = tmp_path / "fuxianzhi-v1.jsonl"
    assert main(["scan", "--root", str(corpus_root), "--output", str(output)]) == 0
    capsys.readouterr()

    exit_code = main(["validate", "--manifest", str(output)])

    assert exit_code == 0
    assert capsys.readouterr().out == "Validated 1 manifest entries\n"


def test_scan_corpus_rejects_same_page_count_with_different_page_locator(tmp_path):
    bundle_dir = tmp_path / "苏州" / "错页样本"
    mismatched = "===== 第 2 页 (folio 1) =====\n正文"
    _write_complete_bundle(bundle_dir, text_by_filename={"text_raw_繁体.txt": mismatched})

    with pytest.raises(CorpusImportError) as caught:
        scan_corpus(tmp_path)

    assert caught.value.code == "page_locator_mismatch"
    assert caught.value.relative_path == "苏州/错页样本"


def test_scan_corpus_rejects_non_continuous_physical_page_sequence(tmp_path):
    bundle_dir = tmp_path / "苏州" / "断页样本"
    skipped_first_page = "===== 第 2 页 (folio 2) =====\n正文"
    _write_complete_bundle(
        bundle_dir,
        text_by_filename={
            "text_raw_简体.txt": skipped_first_page,
            "text_raw_繁体.txt": skipped_first_page,
            "text_简体.txt": skipped_first_page,
            "text_繁体.txt": skipped_first_page,
        },
    )

    with pytest.raises(CorpusImportError) as caught:
        scan_corpus(tmp_path)

    assert caught.value.code == "page_sequence_invalid"
    assert caught.value.relative_path == "苏州/断页样本"


def test_scan_corpus_rejects_symlinked_bundle_asset(tmp_path):
    bundle_dir = tmp_path / "苏州" / "链接样本"
    _write_complete_bundle(bundle_dir)
    external_pdf = tmp_path / "outside.pdf"
    external_pdf.write_bytes(b"%PDF-1.4\noutside")
    (bundle_dir / "book.pdf").unlink()
    try:
        (bundle_dir / "book.pdf").symlink_to(external_pdf)
    except OSError as exc:
        pytest.skip(f"symbolic links are unavailable in this environment: {exc}")

    with pytest.raises(CorpusImportError) as caught:
        scan_corpus(tmp_path)

    assert caught.value.code == "unsafe_symlink"
    assert caught.value.relative_path == "苏州/链接样本/book.pdf"


def test_validate_manifest_rejects_duplicate_bundle_identity(tmp_path):
    corpus_root = tmp_path / "corpus"
    _write_complete_bundle(corpus_root / "太仓" / "太仓州志")
    bundle = scan_corpus(corpus_root).bundles[0]

    with pytest.raises(CorpusImportError) as caught:
        validate_manifest([bundle.model_dump_json(), bundle.model_dump_json()])

    assert caught.value.code == "duplicate_manifest_entry"


def test_scan_corpus_reports_invalid_utf8_with_relative_asset_path(tmp_path):
    bundle_dir = tmp_path / "太仓" / "编码样本"
    _write_complete_bundle(bundle_dir)
    (bundle_dir / "text_繁体.txt").write_bytes(b"\xff\xfeinvalid")

    with pytest.raises(CorpusImportError) as caught:
        scan_corpus(tmp_path)

    assert caught.value.code == "invalid_utf8"
    assert caught.value.relative_path == "太仓/编码样本/text_繁体.txt"


def test_validate_manifest_rejects_bundle_id_that_does_not_match_relative_path(tmp_path):
    corpus_root = tmp_path / "corpus"
    _write_complete_bundle(corpus_root / "苏州" / "稳定标识样本")
    bundle = scan_corpus(corpus_root).bundles[0]
    altered = bundle.model_copy(update={"relative_directory": "苏州/被替换的目录"})

    with pytest.raises(CorpusImportError) as caught:
        validate_manifest([altered.model_dump_json()])

    assert caught.value.code == "bundle_identity_mismatch"


def test_quality_analysis_reports_known_ocr_markers_by_page():
    pages = parse_paginated_texts(
        raw_traditional=StringIO("===== 第 1 页 (folio 1) =====\nb殘留行首\n正文"),
        clean_traditional=StringIO("===== 第 1 页 (folio 1) =====\n缺字□"),
        clean_simplified=StringIO("===== 第 1 页 (folio 1) =====\n替换�"),
    )

    issues = analyze_page_quality(pages)

    assert [(issue.code, issue.field, issue.count, issue.physical_page_number) for issue in issues] == [
        ("raw_line_prefix_b", "raw_traditional", 1, 1),
        ("missing_glyph_placeholder", "clean_traditional", 1, 1),
        ("unicode_replacement_character", "clean_simplified", 1, 1),
    ]


def test_quality_analysis_reports_empty_canonical_clean_page():
    pages = parse_paginated_texts(
        raw_traditional=StringIO("===== 第 1 页 (folio 1) =====\n原始内容"),
        clean_traditional=StringIO("===== 第 1 页 (folio 1) =====\n"),
        clean_simplified=StringIO("===== 第 1 页 (folio 1) =====\n"),
    )

    issues = analyze_page_quality(pages)

    assert [(issue.code, issue.field, issue.physical_page_number) for issue in issues] == [
        ("empty_clean_page", "clean_traditional", 1),
    ]


@pytest.mark.parametrize("relative_directory", ["../outside", "/absolute/path", "苏州\\escaped"])
def test_validate_manifest_rejects_unsafe_relative_directory(tmp_path, relative_directory):
    corpus_root = tmp_path / "corpus"
    _write_complete_bundle(corpus_root / "苏州" / "路径样本")
    bundle = scan_corpus(corpus_root).bundles[0]
    unsafe = bundle.model_copy(
        update={
            "relative_directory": relative_directory,
            "bundle_id": calculate_bundle_id(bundle.corpus_root_id, relative_directory),
        }
    )

    with pytest.raises(CorpusImportError) as caught:
        validate_manifest([unsafe.model_dump_json()])

    assert caught.value.code == "unsafe_relative_path"


def test_scan_corpus_rejects_existing_root_without_any_bundles(tmp_path):
    with pytest.raises(CorpusImportError) as caught:
        scan_corpus(tmp_path)

    assert caught.value.code == "no_bundles_found"


def test_validate_manifest_requires_hash_and_size_for_every_declared_asset(tmp_path):
    corpus_root = tmp_path / "corpus"
    _write_complete_bundle(corpus_root / "苏州" / "资产清单样本")
    bundle = scan_corpus(corpus_root).bundles[0]
    incomplete = bundle.model_copy(update={"hashes": {key: value for key, value in bundle.hashes.items() if key != "book.pdf"}})

    with pytest.raises(CorpusImportError) as caught:
        validate_manifest([incomplete.model_dump_json()])

    assert caught.value.code == "asset_manifest_mismatch"


def test_validate_manifest_rejects_invalid_asset_hash_or_size(tmp_path):
    corpus_root = tmp_path / "corpus"
    _write_complete_bundle(corpus_root / "苏州" / "资产元数据样本")
    bundle = scan_corpus(corpus_root).bundles[0]
    invalid_hashes = dict(bundle.hashes)
    invalid_hashes["book.pdf"] = "not-a-sha256"
    invalid_sizes = dict(bundle.sizes)
    invalid_sizes["book.pdf"] = -1
    invalid = bundle.model_copy(update={"hashes": invalid_hashes, "sizes": invalid_sizes})

    with pytest.raises(CorpusImportError) as caught:
        validate_manifest([invalid.model_dump_json()])

    assert caught.value.code == "invalid_asset_metadata"


def test_validate_manifest_accepts_a_bundle_directly_under_the_corpus_root(tmp_path):
    _write_complete_bundle(tmp_path / "包山集四卷")
    bundle = scan_corpus(tmp_path).bundles[0]

    assert validate_manifest((bundle.model_dump_json(),)) == (bundle,)


def test_plan_import_rejects_an_asset_changed_after_the_manifest_was_scanned(tmp_path):
    bundle_dir = tmp_path / "苏州" / "漂移样本"
    _write_complete_bundle(bundle_dir)
    bundle = scan_corpus(tmp_path).bundles[0]
    (bundle_dir / "book.pdf").write_bytes(b"changed after scan")

    with pytest.raises(CorpusImportError) as caught:
        plan_import(tmp_path, (bundle,))

    assert caught.value.code == "source_asset_changed"
    assert caught.value.relative_path == "苏州/漂移样本/book.pdf"


def test_load_bundle_pages_preserves_all_four_text_variants(tmp_path):
    bundle_dir = tmp_path / "苏州" / "四种文本"
    variants = {
        "text_raw_简体.txt": "===== 第 1 页 (folio 一) =====\n原始简体",
        "text_raw_繁体.txt": "===== 第 1 页 (folio 一) =====\n原始繁體",
        "text_简体.txt": "===== 第 1 页 (folio 一) =====\n清理简体",
        "text_繁体.txt": "===== 第 1 页 (folio 一) =====\n清理繁體",
    }
    _write_complete_bundle(bundle_dir, text_by_filename=variants)
    bundle = scan_corpus(tmp_path).bundles[0]

    pages = load_bundle_pages(tmp_path, bundle)

    assert len(pages) == 1
    assert pages[0].folio_label == "一"
    assert pages[0].raw_simplified == "原始简体"
    assert pages[0].raw_traditional == "原始繁體"
    assert pages[0].clean_simplified == "清理简体"
    assert pages[0].clean_traditional == "清理繁體"


def test_plan_import_allows_technical_dry_run_but_reports_governance_blockers(tmp_path):
    bundle_dir = tmp_path / "苏州" / "待治理样本"
    _write_complete_bundle(bundle_dir)
    bundle = scan_corpus(tmp_path).bundles[0]

    report = plan_import(tmp_path, (bundle,), bundle_selector="待治理样本")

    assert report.bundle_count == 1
    assert report.page_count == 1
    assert report.can_commit is False
    assert set(report.blockers) == {"source_level_missing", "source_institution_missing", "holder_missing"}


def test_build_import_bundle_can_create_an_internal_unrated_working_copy(tmp_path):
    bundle_dir = tmp_path / "吴江" / "内部工作样本"
    _write_complete_bundle(bundle_dir)
    manifest = scan_corpus(tmp_path).bundles[0]

    imported = build_import_bundle(
        tmp_path,
        manifest,
        actor_id="admin-1",
        generated_at=datetime(2026, 8, 22, tzinfo=UTC),
        chunking_policy=ChunkingPolicy(split_version="fuxianzhi-v1", max_characters=200, overlap_characters=20),
        allow_unconfirmed_internal=True,
    )

    assert imported.document.source_level.value == "U"
    assert imported.document.source_institution == "unconfirmed"
    assert imported.document.holder == "unconfirmed"
    assert imported.document.visibility_scope.value == "internal"
    assert [item.value for item in imported.document.authorized_uses] == ["internal_processing"]
    assert imported.document.authorization_status.value == "active"
    assert imported.document.authorization_basis == "Project owner approved internal corpus processing; public use remains unconfirmed"


def test_build_import_bundle_uses_precomputed_provenance_without_fabricated_image_metadata(tmp_path):
    bundle_dir = tmp_path / "苏州" / "预计算样本"
    _write_complete_bundle(bundle_dir)
    scanned = scan_corpus(tmp_path).bundles[0]
    bundle = scanned.model_copy(update={"source_level": "B", "source_institution": "测试馆", "holder": "测试馆"})
    generated_at = datetime(2026, 8, 22, tzinfo=UTC)

    imported = build_import_bundle(
        tmp_path,
        bundle,
        actor_id="admin-1",
        generated_at=generated_at,
        chunking_policy=ChunkingPolicy(split_version="fuxianzhi-v1", max_characters=200, overlap_characters=20),
    )

    assert imported.document.id == f"fuxianzhi-{bundle.bundle_id}"
    assert imported.source_file.sha256 == bundle.hashes["book.pdf"]
    assert imported.object_metadata.backend == "mounted"
    assert imported.object_metadata.storage_uri == f"corpus://fuxianzhi/{bundle.relative_directory}/book.pdf"
    assert len(imported.ocr_attempts) == 1
    attempt = imported.ocr_attempts[0]
    assert attempt.provider_name == "precomputed-corpus"
    assert attempt.mean_confidence is None
    assert attempt.image_sha256 is None
    assert attempt.image_width is None
    assert attempt.image_height is None
    assert attempt.folio_label == "1"
    assert imported.cleaned_pages[0].clean_text == "正文"
    assert imported.chunk_set.chunks[0].cleaned_page_ids == (imported.cleaned_pages[0].id,)
    assert imported.ingestion_job.status is IngestionJobStatus.AWAITING_REVIEW
    assert imported.ingestion_job.current_step is IngestionStepName.REVIEW
    assert imported.ingestion_job.step(IngestionStepName.CHUNK).status is IngestionStepStatus.COMPLETED
    assert len(imported.ingestion_events) == 9


def test_build_import_bundle_is_deterministic_for_the_same_manifest(tmp_path):
    bundle_dir = tmp_path / "苏州" / "幂等样本"
    _write_complete_bundle(bundle_dir)
    scanned = scan_corpus(tmp_path).bundles[0]
    bundle = scanned.model_copy(update={"source_level": "B", "source_institution": "测试馆", "holder": "测试馆"})
    policy = ChunkingPolicy(split_version="fuxianzhi-v1", max_characters=200, overlap_characters=20)

    first = build_import_bundle(tmp_path, bundle, actor_id="admin-1", generated_at=datetime(2026, 8, 22, tzinfo=UTC), chunking_policy=policy)
    second = build_import_bundle(tmp_path, bundle, actor_id="admin-2", generated_at=datetime(2026, 8, 23, tzinfo=UTC), chunking_policy=policy)

    assert first.document.id == second.document.id
    assert first.source_file.id == second.source_file.id
    assert [page.id for page in first.cleaned_pages] == [page.id for page in second.cleaned_pages]
    assert first.chunk_set.id == second.chunk_set.id
    assert [chunk.id for chunk in first.chunk_set.chunks] == [chunk.id for chunk in second.chunk_set.chunks]


def test_import_cli_dry_run_reports_blockers_without_writing_a_database(tmp_path, capsys):
    corpus_root = tmp_path / "corpus"
    _write_complete_bundle(corpus_root / "包山集四卷")
    manifest_path = tmp_path / "manifest.jsonl"
    manifest_path.write_text(scan_corpus(corpus_root).bundles[0].model_dump_json() + "\n", encoding="utf-8")

    exit_code = main(
        [
            "import",
            "--manifest",
            str(manifest_path),
            "--root",
            str(corpus_root),
            "--bundle",
            "包山集四卷",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["bundle_count"] == 1
    assert payload["page_count"] == 1
    assert payload["can_commit"] is False
    assert "source_level_missing" in payload["blockers"]
