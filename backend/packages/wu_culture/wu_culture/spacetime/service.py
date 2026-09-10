from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field


class TimeMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    raw: str
    dynasty: str | None
    year_start: int | None
    year_end: int | None
    confidence: float = Field(ge=0, le=1)
    note: str


_CN_YEAR = r"(?P<year>\d{1,2}|元|正|[一二三四五六七八九十]+)"
_QIANLONG = re.compile('乾隆\\s*' + _CN_YEAR + '\\s*年')
_DAOGUANG = re.compile('道光\\s*' + _CN_YEAR + '\\s*年')
_KANGXI = re.compile('康熙\\s*' + _CN_YEAR + '\\s*年')
_ABS = re.compile(r"(?P<year>\d{3,4})\s*" + '年')


def _cn_year_to_int(token: str) -> int:
    token = token.strip()
    if token.isdigit():
        return int(token)
    if token in {"元", "正"}:
        return 1
    digits = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    if token == "十":
        return 10
    if token.startswith("十"):
        return 10 + digits.get(token[1:], 0)
    if token.endswith("十") and len(token) == 2:
        return digits[token[0]] * 10
    if "十" in token:
        left, right = token.split("十", 1)
        return digits.get(left, 1) * 10 + digits.get(right, 0)
    total = 0
    for ch in token:
        total = total * 10 + digits.get(ch, 0)
    return total


def map_time_label(raw: str) -> TimeMapping:
    text = raw.strip()
    for pattern, dynasty, base in (
        (_QIANLONG, "qing", 1736),
        (_DAOGUANG, "qing", 1821),
        (_KANGXI, "qing", 1662),
    ):
        match = pattern.search(text)
        if match:
            year = base + _cn_year_to_int(match.group("year")) - 1
            return TimeMapping(raw=raw, dynasty=dynasty, year_start=year, year_end=year, confidence=0.8, note="era_year_rule")
    match = _ABS.search(text)
    if match:
        year = int(match.group("year"))
        return TimeMapping(raw=raw, dynasty=None, year_start=year, year_end=year, confidence=0.6, note="absolute_year")
    return TimeMapping(raw=raw, dynasty=None, year_start=None, year_end=None, confidence=0.0, note="unmapped")
