from __future__ import annotations

import re

_PAGE_MARKER = re.compile(r"^===== 第 (?P<page>[1-9][0-9]*) 页 \(folio (?P<folio>[^)]+)\) =====$")


def parse_page_marker(line: str) -> tuple[int, str] | None:
    marker = _PAGE_MARKER.fullmatch(line)
    if marker is None:
        return None
    return int(marker.group("page")), marker.group("folio").strip()
