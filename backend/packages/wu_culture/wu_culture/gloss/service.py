from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GlossSentence(_M):
    original: str
    modern: str
    keywords: tuple[dict[str, str], ...] = ()
    uncertain_terms: tuple[str, ...] = ()


class GlossResult(_M):
    original: str
    sentences: tuple[GlossSentence, ...]
    notes: tuple[str, ...] = ()


_TERM_GLOSS = {
    "缘溪行": "沿着溪水前行",
    "远近": "路程的远近",
    "忽逢": "忽然遇见",
    "夹岸": "分布在溪流两岸",
    "芳草鲜美": "花草鲜艳美丽",
    "落英": "落花",
    "缤纷": "繁多而纷乱的样子",
    "诣": "到、前往",
    "既而": "不久",
    "遂": "于是、就",
    "桥": "桥梁",
    "始建": "最初建造",
    "重修": "再次修缮",
    "未详": "尚未考证清楚",
}


def gloss_passage(text: str, *, max_chars: int = 2000) -> GlossResult:
    if not text or not text.strip():
        raise ValueError("empty passage")
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    original = text.strip()
    truncated = len(original) > max_chars
    if truncated:
        original = original[: max_chars - 1] + "…"
    parts = [part for part in re.split(r"(?<=[。！？；])", original) if part.strip()]
    sentences: list[GlossSentence] = []
    for part in parts:
        keywords = []
        modern = part
        for term, meaning in _TERM_GLOSS.items():
            if term in part:
                keywords.append({"term": term, "meaning": meaning})
                modern = modern.replace(term, meaning)
        uncertain = tuple(term for term in ("未详", "待考") if term in part)
        sentences.append(
            GlossSentence(
                original=part,
                modern=modern,
                keywords=tuple(keywords),
                uncertain_terms=uncertain,
            )
        )
    return GlossResult(
        original=original,
        sentences=tuple(sentences),
        notes=(
            "释读仅供阅读辅助，不是权威校注。",
            "原文始终并列保留，不能将释读文字作为原文引用。",
        )
        + (("输入篇幅超过上限，内容已截断。",) if truncated else ()),
    )
