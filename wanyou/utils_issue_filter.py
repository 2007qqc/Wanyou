import datetime as dt
import os
import re
from pathlib import Path
from typing import Optional, Set

import config
from wanyou.run_clock import effective_run_date, effective_run_datetime


def current_issue_cutoff(now: Optional[dt.datetime] = None) -> dt.datetime:
    override = str(getattr(config, "NOTICE_PREFILTER_CUTOFF", "") or "").strip()
    if override:
        parsed = parse_datetime_text(override)
        if parsed is not None:
            return parsed
    current = effective_run_datetime(now)
    cutoff = current - dt.timedelta(days=7)
    return cutoff.replace(second=0, microsecond=0)



def parse_datetime_text(text: str) -> Optional[dt.datetime]:
    raw = (text or "").strip()
    if not raw:
        return None

    year_first = re.search(
        r"(20\d{2})[年\-/.](\d{1,2})[月\-/.](\d{1,2})(?:日)?(?:\s+(\d{1,2})[:：](\d{2}))?",
        raw,
    )
    if year_first:
        return _safe_datetime(
            int(year_first.group(1)),
            int(year_first.group(2)),
            int(year_first.group(3)),
            int(year_first.group(4) or 0),
            int(year_first.group(5) or 0),
        )

    month_day = re.search(
        r"(\d{1,2})月(\d{1,2})日(?:\s*(\d{1,2})[:：](\d{2}))?",
        raw,
    )
    if month_day:
        current_year = effective_run_date().year
        return _safe_datetime(
            current_year,
            int(month_day.group(1)),
            int(month_day.group(2)),
            int(month_day.group(3) or 0),
            int(month_day.group(4) or 0),
        )

    return None


def should_skip_by_time(date_text: str, cutoff: Optional[dt.datetime] = None) -> bool:
    parsed = parse_datetime_text(date_text)
    if parsed is None:
        return False
    return parsed < (cutoff or current_issue_cutoff())



def load_previous_titles(current_markdown_path: str = "") -> Set[str]:
    _ = current_markdown_path
    return set()


def seen_in_previous_issue(title: str, previous_titles: Set[str]) -> bool:
    _ = title, previous_titles
    return False


def normalize_title_key(title: str) -> str:
    cleaned = re.sub(r"\s+", "", title or "")
    cleaned = re.sub(r"[\[\](){}、，,：:\|?/\\\-]", "", cleaned)
    return cleaned.lower().strip()



def _extract_report_timestamp(path_text: str) -> Optional[dt.datetime]:
    basename = os.path.basename(path_text or "")
    match = re.match(rf"{re.escape(getattr(config, 'OUTPUT_NAME_PREFIX', 'wanyou'))}_(\d{{8}}_\d{{4}})(?:_raw)?\.md$", basename)
    if not match:
        return None
    try:
        return dt.datetime.strptime(match.group(1), "%Y%m%d_%H%M")
    except Exception:
        return None



def _safe_datetime(year: int, month: int, day: int, hour: int, minute: int) -> Optional[dt.datetime]:
    hour = min(max(hour, 0), 23)
    minute = min(max(minute, 0), 59)
    try:
        return dt.datetime(year, month, day, hour, minute)
    except Exception:
        return None
