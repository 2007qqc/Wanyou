
import datetime as dt
import re
from typing import Dict, List, Optional

from wanyou.run_clock import effective_run_datetime
from wanyou.utils_issue_filter import current_issue_cutoff, parse_datetime_text

DEADLINE_KEYWORDS = [
    "截止", "截止时间", "截止日期", "报名截止", "申请截止",
    "提交截止", "截至", "报名时间", "申请时间", "deadline", "due",
]
EVENT_KEYWORDS = [
    "活动时间", "报告时间", "讲座时间", "举办时间", "开始时间",
    "比赛时间", "培训时间", "日程", "宣讲会",
]
PUBLISH_KEYWORDS = ["发布时间", "发布日期", "发布"]

DATE_PATTERN = re.compile(
    r"(20\d{2}[年\-/.]\d{1,2}[月\-/.]\d{1,2}(?:日)?(?:\s*(?:周[一二三四五六日天])?)?(?:\s*\d{1,2}[:：]\d{2})?"
    r"|\d{1,2}月\d{1,2}日(?:\s*(?:周[一二三四五六日天])?)?(?:\s*\d{1,2}[:：]\d{2})?)"
)
TIME_PATTERN = re.compile(r"(\d{1,2})[:：](\d{2})")


def _line_kind(line: str) -> str:
    lower = line.lower()
    if any(keyword.lower() in lower for keyword in DEADLINE_KEYWORDS):
        return "deadline"
    if any(keyword.lower() in lower for keyword in PUBLISH_KEYWORDS):
        return "publish"
    if any(keyword.lower() in lower for keyword in EVENT_KEYWORDS):
        return "event"
    return "mentioned"


def _has_explicit_time(text: str) -> bool:
    return bool(TIME_PATTERN.search(text or ""))


def _normalize_dt(parsed: Optional[dt.datetime], kind: str, raw: str) -> Optional[dt.datetime]:
    if parsed is None:
        return None
    if _has_explicit_time(raw):
        return parsed
    if kind in {"deadline", "event"}:
        return parsed.replace(hour=23, minute=59)
    return parsed


def extract_temporal_signals(text: str, fallback_publish_date: str = "", now: Optional[dt.datetime] = None) -> List[Dict[str, str]]:
    current = now or effective_run_datetime()
    signals: List[Dict[str, str]] = []
    seen = set()

    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    for line in lines:
        kind = _line_kind(line)
        for match in DATE_PATTERN.finditer(line):
            raw = match.group(1).strip()
            parsed = _normalize_dt(parse_datetime_text(raw), kind, raw)
            key = (kind, raw, parsed.isoformat(timespec="minutes") if parsed else "")
            if key in seen:
                continue
            seen.add(key)
            signals.append(
                {
                    "kind": kind,
                    "raw": raw,
                    "parsed": parsed.isoformat(timespec="minutes") if parsed else "",
                    "context": line[:180],
                }
            )

    if fallback_publish_date:
        parsed = _normalize_dt(parse_datetime_text(fallback_publish_date), "publish", fallback_publish_date)
        key = ("publish", fallback_publish_date, parsed.isoformat(timespec="minutes") if parsed else "")
        if key not in seen:
            signals.append(
                {
                    "kind": "publish",
                    "raw": fallback_publish_date,
                    "parsed": parsed.isoformat(timespec="minutes") if parsed else "",
                    "context": "fallback_publish_date",
                }
            )
    return signals


def _parsed_datetimes(signals: List[Dict[str, str]], kind: str) -> List[dt.datetime]:
    values = []
    for signal in signals:
        if signal.get("kind") != kind or not signal.get("parsed"):
            continue
        try:
            values.append(dt.datetime.fromisoformat(signal["parsed"]))
        except Exception:
            continue
    return values


def assess_temporal_relevance(
    *,
    text: str,
    fallback_publish_date: str = "",
    now: Optional[dt.datetime] = None,
    cutoff: Optional[dt.datetime] = None,
) -> Dict[str, object]:
    current = now or effective_run_datetime()
    issue_cutoff = cutoff or current_issue_cutoff(current)
    signals = extract_temporal_signals(text, fallback_publish_date=fallback_publish_date, now=current)
    deadlines = _parsed_datetimes(signals, "deadline")
    events = _parsed_datetimes(signals, "event")
    publishes = _parsed_datetimes(signals, "publish")

    if deadlines:
        latest = max(deadlines)
        return {
            "keep": latest >= current,
            "reason": "deadline_active" if latest >= current else "deadline_expired",
            "basis": latest.isoformat(timespec="minutes"),
            "signals": signals,
            "cutoff": issue_cutoff.isoformat(timespec="minutes"),
            "now": current.isoformat(timespec="minutes"),
        }

    if events:
        latest = max(events)
        grace = current - dt.timedelta(hours=12)
        return {
            "keep": latest >= grace,
            "reason": "event_active" if latest >= grace else "event_expired",
            "basis": latest.isoformat(timespec="minutes"),
            "signals": signals,
            "cutoff": issue_cutoff.isoformat(timespec="minutes"),
            "now": current.isoformat(timespec="minutes"),
        }

    if publishes:
        latest = max(publishes)
        return {
            "keep": latest >= issue_cutoff,
            "reason": "publish_recent" if latest >= issue_cutoff else "publish_older_than_cutoff",
            "basis": latest.isoformat(timespec="minutes"),
            "signals": signals,
            "cutoff": issue_cutoff.isoformat(timespec="minutes"),
            "now": current.isoformat(timespec="minutes"),
        }

    return {
        "keep": True,
        "reason": "no_parseable_date_keep",
        "basis": "",
        "signals": signals,
        "cutoff": issue_cutoff.isoformat(timespec="minutes"),
        "now": current.isoformat(timespec="minutes"),
    }


def should_drop_by_temporal_relevance(text: str, fallback_publish_date: str = "") -> Dict[str, object]:
    assessment = assess_temporal_relevance(text=text, fallback_publish_date=fallback_publish_date)
    assessment["drop"] = not bool(assessment.get("keep"))
    return assessment
