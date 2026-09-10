from __future__ import annotations

from wu_culture.chunking import ChunkingPolicy, ChunkSourcePage, chunk_cleaned_pages


def test_same_structured_page_produces_stable_volume_item_paragraph_chunks():
    page = ChunkSourcePage(
        cleaned_page_id="cleaned-page-1-g1",
        page_number=1,
        raw_text="卷一 山川\n目一 木渎\n木渎位于太湖之滨。\n\n街巷沿河展开。",
        clean_text="卷一 山川\n目一 木渎\n木渎位于太湖之滨。\n\n街巷沿河展开。",
    )
    policy = ChunkingPolicy(split_version="structure-v1", max_characters=200, overlap_characters=20)

    first = chunk_cleaned_pages(document_id="source-1", source_file_id="file-1", pages=(page,), policy=policy)
    second = chunk_cleaned_pages(document_id="source-1", source_file_id="file-1", pages=(page,), policy=policy)

    assert first == second
    assert [(chunk.volume, chunk.item, chunk.paragraph_index, chunk.clean_text) for chunk in first.chunks] == [
        ("卷一 山川", "目一 木渎", 0, "木渎位于太湖之滨。"),
        ("卷一 山川", "目一 木渎", 1, "街巷沿河展开。"),
    ]
    assert all(chunk.page_start == 1 and chunk.page_end == 1 for chunk in first.chunks)
    assert len({chunk.id for chunk in first.chunks}) == 2
    assert first.structure[0].title == "卷一 山川"
    assert first.structure[0].children[0].title == "目一 木渎"


def test_unfinished_paragraph_continues_across_physical_pages():
    pages = (
        ChunkSourcePage(
            cleaned_page_id="cleaned-page-1-g1",
            page_number=1,
            raw_text="卷一\n目一\n木渎沿河",
            clean_text="卷一\n目一\n木渎沿河",
        ),
        ChunkSourcePage(
            cleaned_page_id="cleaned-page-2-g1",
            page_number=2,
            raw_text="而建，街巷相连。\n\n第二段。",
            clean_text="而建，街巷相连。\n\n第二段。",
        ),
    )

    result = chunk_cleaned_pages(
        document_id="source-1",
        source_file_id="file-1",
        pages=pages,
        policy=ChunkingPolicy(split_version="structure-v1", max_characters=200, overlap_characters=20),
    )

    assert [(chunk.clean_text, chunk.page_start, chunk.page_end, chunk.cleaned_page_ids) for chunk in result.chunks] == [
        ("木渎沿河而建，街巷相连。", 1, 2, ("cleaned-page-1-g1", "cleaned-page-2-g1")),
        ("第二段。", 2, 2, ("cleaned-page-2-g1",)),
    ]


def test_long_paragraph_uses_bounded_overlapping_windows_without_orphans():
    text = "".join(str(index % 10) for index in range(120))
    page = ChunkSourcePage(
        cleaned_page_id="cleaned-page-1-g1",
        page_number=1,
        raw_text=text,
        clean_text=text,
    )

    result = chunk_cleaned_pages(
        document_id="source-1",
        source_file_id="file-1",
        pages=(page,),
        policy=ChunkingPolicy(split_version="structure-v1", max_characters=50, overlap_characters=10),
    )

    assert [(chunk.paragraph_char_start, chunk.paragraph_char_end) for chunk in result.chunks] == [(0, 50), (40, 90), (80, 120)]
    assert [chunk.clean_text for chunk in result.chunks] == [text[0:50], text[40:90], text[80:120]]
    assert [chunk.paragraph_index for chunk in result.chunks] == [0, 0, 0]
    assert result.chunks[0].clean_text[-10:] == result.chunks[1].clean_text[:10]
    assert result.chunks[1].clean_text[-10:] == result.chunks[2].clean_text[:10]


def test_chunk_clean_text_projects_back_to_ocr_raw_text():
    page = ChunkSourcePage(
        cleaned_page_id="cleaned-page-1-g1",
        page_number=1,
        raw_text="後臺\n史料",
        clean_text="后台史料",
    )

    result = chunk_cleaned_pages(
        document_id="source-1",
        source_file_id="file-1",
        pages=(page,),
        policy=ChunkingPolicy(split_version="structure-v1", max_characters=200, overlap_characters=20),
    )

    assert len(result.chunks) == 1
    assert result.chunks[0].clean_text == "后台史料"
    assert result.chunks[0].raw_text == "後臺\n史料"


def test_chunk_falls_back_to_source_page_when_clean_text_has_no_raw_overlap():
    inserted = "新增校訂內容" * 12
    page = ChunkSourcePage(
        cleaned_page_id="cleaned-page-1-g1",
        page_number=1,
        raw_text="原始繁體頁面",
        clean_text=f"{inserted}原始繁體頁面",
    )

    result = chunk_cleaned_pages(
        document_id="source-1",
        source_file_id="file-1",
        pages=(page,),
        policy=ChunkingPolicy(
            split_version="structure-v1",
            max_characters=50,
            overlap_characters=10,
        ),
    )

    assert result.chunks[0].clean_text == inserted[:50]
    assert result.chunks[0].raw_text == "原始繁體頁面"
