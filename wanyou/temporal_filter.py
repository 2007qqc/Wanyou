
import datetime as dt
import re
from typing import Dict, List, Optional

from wanyou.run_clock import effective_publish_datetime, effective_run_datetime
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
    r"(20\d{2}[年\-/.]\d{1,2}[月\-/.]\d{1,2}(?:[日号])?(?:\s*(?:周[一二三四五六日天])?)?(?:\s*\d{1,2}[:：]\d{2})?"
    r"|\d{1,2}月\d{1,2}[日号](?:\s*(?:周[一二三四五六日天])?)?(?:\s*\d{1,2}[:：]\d{2})?)"
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
    expiry_now: Optional[dt.datetime] = None,
) -> Dict[str, object]:
    """判断一条信息是否还值得放进这一期。

    `now` 指本期的覆盖窗口（WANYOU_RUN_DATE），用来判断「发布时间够不够新」；
    `expiry_now` 指**见刊日**（默认窗口结束后那个周一），用来判断「截止时间/活动时间
    是不是已经过了」。两个时钟分开是必须的：公众号文章可能是 10.19 发的（对窗口来说
    很新），但它报名的活动 10.22 就结束了，见刊时已经过期。
    """
    current = now or effective_run_datetime()
    expiry = expiry_now or effective_publish_datetime()
    issue_cutoff = cutoff or current_issue_cutoff(current)
    signals = extract_temporal_signals(text, fallback_publish_date=fallback_publish_date, now=current)
    deadlines = _parsed_datetimes(signals, "deadline")
    events = _parsed_datetimes(signals, "event")
    publishes = _parsed_datetimes(signals, "publish")
    mentions = _parsed_datetimes(signals, "mentioned")

    if deadlines:
        latest = max(deadlines)
        # 见刊日当天的截止时间不再保留：这一期在见刊日早上发，读者看到时当天
        # 的截止往往已经进入最后时限/已经处理过；往期也出现过把“次周周一截止”
        # 当成有效截止的情况，而那天正是报纸刊登日。
        keep = latest.date() > expiry.date()
        if keep:
            reason = "deadline_active"
        elif latest.date() == expiry.date():
            reason = "deadline_on_publish_day"
        else:
            reason = "deadline_expired"
        return {
            "keep": keep,
            "reason": reason,
            "basis": latest.isoformat(timespec="minutes"),
            "signals": signals,
            "cutoff": issue_cutoff.isoformat(timespec="minutes"),
            "now": current.isoformat(timespec="minutes"),
            "expiry_now": expiry.isoformat(timespec="minutes"),
        }

    if events:
        latest = max(events)
        grace = expiry - dt.timedelta(hours=12)
        return {
            "keep": latest >= grace,
            "reason": "event_active" if latest >= grace else "event_expired",
            "basis": latest.isoformat(timespec="minutes"),
            "signals": signals,
            "cutoff": issue_cutoff.isoformat(timespec="minutes"),
            "now": current.isoformat(timespec="minutes"),
            "expiry_now": expiry.isoformat(timespec="minutes"),
        }

    if publishes:
        latest = max(publishes)
        future_mentions = [value for value in mentions if value >= expiry - dt.timedelta(hours=12)]
        if latest < issue_cutoff and future_mentions:
            basis = max(future_mentions)
            return {
                "keep": True,
                "reason": "publish_old_but_future_mentioned",
                "basis": basis.isoformat(timespec="minutes"),
                "signals": signals,
                "cutoff": issue_cutoff.isoformat(timespec="minutes"),
                "now": current.isoformat(timespec="minutes"),
                "expiry_now": expiry.isoformat(timespec="minutes"),
            }
        return {
            "keep": latest >= issue_cutoff,
            "reason": "publish_recent" if latest >= issue_cutoff else "publish_older_than_cutoff",
            "basis": latest.isoformat(timespec="minutes"),
            "signals": signals,
            "cutoff": issue_cutoff.isoformat(timespec="minutes"),
            "now": current.isoformat(timespec="minutes"),
            "expiry_now": expiry.isoformat(timespec="minutes"),
        }

    return {
        "keep": True,
        "reason": "no_parseable_date_keep",
        "basis": "",
        "signals": signals,
        "cutoff": issue_cutoff.isoformat(timespec="minutes"),
        "now": current.isoformat(timespec="minutes"),
        "expiry_now": expiry.isoformat(timespec="minutes"),
    }
