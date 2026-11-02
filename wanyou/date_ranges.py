"""日期解析：把公众号正文里真实出现的写法都认出来。

`wechat_freshness` 原本只认「11月7日」「2026年11月7日」。于是最常见的两种写法
——「活动时间：11.5」和「11月7—8日」——被解析成空列表，规则短路，改由 LLM 判断；
LLM 又反过来把**未来**的日期说成「早于见刊日」。已复现：2026-11-02 这期，
《无偿献血》写的是 11.7–11.8，被判 `llm:expired:活动日期11月7—8日，早于见刊日` 丢掉。

这里把下面这些写法统一成 ``datetime.date`` 列表：

* ``2026年11月7日`` / ``2026-11-07`` / ``2026.11.7`` / ``2026/11/7``
* ``11月7日`` / ``11月7号``
* 区间：``11月7—8日``、``11月7-8日``、``11月7~8日``、``11月7至8日``（展开成两天，
  跨月 ``11月30日—12月2日`` 也认）
* 数值：``11.5``、``11/7``、``11.7-11.8``、``11.7—8``

数值写法必须出现在有日期语境的同一行里（活动/时间/截止/报名/周X…），否则
``v1.5``、``3.5万``、``coverage 12.5%`` 都会被误当成 1 月 5 日。
"""

from __future__ import annotations

import datetime as dt
import re
from typing import List, Optional

# 数值日期必须有语境，避免版本号/百分比/小数被当成日期
_CONTEXT_RE = re.compile(
    r"活动|时间|日期|截止|截至|报名|举办|举行|开始|结束|开放|领票|周[一二三四五六日天]"
)

_YEAR_FORM = re.compile(r"(20\d{2})\s*[年./\-]\s*(\d{1,2})\s*[月./\-]\s*(\d{1,2})\s*[日号]?")
_MONTH_RANGE = re.compile(
    r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?\s*[—–~～\-至到]+\s*(?:(\d{1,2})\s*月\s*)?(\d{1,2})\s*[日号]"
)
_MONTH_DAY = re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")
_NUM_RANGE = re.compile(
    r"(?<![\d.])(\d{1,2})[./](\d{1,2})(?![\d.])\s*[—–~～\-至到]+\s*(\d{1,2})[./](\d{1,2})(?![\d.])"
)
_NUM_DAY_RANGE = re.compile(
    r"(?<![\d.])(\d{1,2})[./](\d{1,2})(?![\d.])\s*[—–~～\-至到]+\s*(\d{1,2})(?![\d.])"
)
_NUM = re.compile(r"(?<![\d.])(\d{1,2})[./](\d{1,2})(?![\d.])")

_DEADLINE_LINE_RE = re.compile(r"截止|截至|报名至|报名截止|截止时间|报名时间|报名日期")


def _safe(year: int, month: int, day: int) -> Optional[dt.date]:
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def _line_at(text: str, index: int) -> str:
    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    if end == -1:
        end = len(text)
    return text[start:end]


def _roll_forward(dates: List[dt.date], reference: Optional[dt.date]) -> List[dt.date]:
    """12 月的推文里写「1月10日」，指的是明年。"""

    if reference is None:
        return dates
    fixed: List[dt.date] = []
    for value in dates:
        if (reference - value).days > 180:
            nxt = _safe(value.year + 1, value.month, value.day)
            fixed.append(nxt or value)
        else:
            fixed.append(value)
    return fixed


def parse_dates(text: str, year: Optional[int] = None, reference: Optional[dt.date] = None) -> List[dt.date]:
    """返回文本里出现的所有日期（按出现顺序去重）。

    ``year`` 用于补全「11月7日」这类没有年份的写法；``reference``（通常是见刊日/发布日）
    用于把跨年写法滚到下一年。
    """

    if not text:
        return []

    base_year = year or (reference.year if reference else dt.date.today().year)
    found: List[dt.date] = []
    work = text

    def consume(pattern: re.Pattern, handler) -> None:
        nonlocal work

        def repl(match: "re.Match[str]") -> str:
            for value in handler(match):
                if value is not None:
                    found.append(value)
            return " " * len(match.group(0))

        work = pattern.sub(repl, work)

    consume(
        _YEAR_FORM,
        lambda m: [_safe(int(m.group(1)), int(m.group(2)), int(m.group(3)))],
    )

    def month_range(match: "re.Match[str]") -> List[dt.date]:
        month1, day1 = int(match.group(1)), int(match.group(2))
        month2 = int(match.group(3)) if match.group(3) else month1
        day2 = int(match.group(4))
        start = _safe(base_year, month1, day1)
        end = _safe(base_year, month2, day2)
        return [start, end]

    consume(_MONTH_RANGE, month_range)

    def num_range(match: "re.Match[str]") -> List[dt.date]:
        return [
            _safe(base_year, int(match.group(1)), int(match.group(2))),
            _safe(base_year, int(match.group(3)), int(match.group(4))),
        ]

    consume(_NUM_RANGE, num_range)

    def num_day_range(match: "re.Match[str]") -> List[dt.date]:
        month = int(match.group(1))
        return [_safe(base_year, month, int(match.group(2))), _safe(base_year, month, int(match.group(3)))]

    consume(_NUM_DAY_RANGE, num_day_range)
    consume(
        _MONTH_DAY,
        lambda m: [_safe(base_year, int(m.group(1)), int(m.group(2)))],
    )

    def numeric(match: "re.Match[str]") -> List[dt.date]:
        if not _CONTEXT_RE.search(_line_at(text, match.start())):
            return []
        return [_safe(base_year, int(match.group(1)), int(match.group(2)))]

    consume(_NUM, numeric)

    ordered: List[dt.date] = []
    for value in _roll_forward(found, reference):
        if value not in ordered:
            ordered.append(value)
    return ordered


def parse_deadline_dates(text: str, year: Optional[int] = None, reference: Optional[dt.date] = None) -> List[dt.date]:
    """只解析「截止/报名截止」这类行里的日期。"""

    if not text:
        return []
    hits: List[dt.date] = []
    for line in text.splitlines():
        if not _DEADLINE_LINE_RE.search(line):
            continue
        hits.extend(parse_dates(line, year, reference))
    return list(dict.fromkeys(hits))
