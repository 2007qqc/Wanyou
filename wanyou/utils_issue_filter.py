import datetime as dt
import re
from typing import Optional

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
        r"(20\d{2})[年\-/.](\d{1,2})[月\-/.](\d{1,2})(?:[日号])?(?:\s+(\d{1,2})[:：](\d{2}))?",
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
        r"(\d{1,2})月(\d{1,2})[日号](?:\s*(\d{1,2})[:：](\d{2}))?",
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


def published_in_current_window(date_text: str, window_start: Optional[dt.date] = None) -> bool:
    """公告是否在「本期覆盖窗口」内发布（窗口首日 = WANYOU_RUN_DATE）。

    往期报纸已经登过的公告（如开学初的宿舍熄灯通知）不再重复选入；只有本期
    窗口内发布的公告才进入候选。解析不出日期时保守放行。
    """
    parsed = parse_datetime_text(date_text)
    if parsed is None:
        return True
    start = window_start or effective_run_date()
    return parsed.date() >= start



def _safe_datetime(year: int, month: int, day: int, hour: int, minute: int) -> Optional[dt.datetime]:
    hour = min(max(hour, 0), 23)
    minute = min(max(minute, 0), 59)
    try:
        return dt.datetime(year, month, day, hour, minute)
    except Exception:
        return None
