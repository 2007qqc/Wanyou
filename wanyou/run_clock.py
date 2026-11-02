import datetime as dt
import os
from typing import Optional


def _parse_override(name: str) -> Optional[dt.date]:
    override = os.environ.get(name, "").strip()
    if not override:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return dt.datetime.strptime(override, fmt).date()
        except ValueError:
            continue
    return None


def effective_run_date(now: Optional[dt.datetime] = None) -> dt.date:
    parsed = _parse_override("WANYOU_RUN_DATE")
    if parsed:
        return parsed
    return (now or dt.datetime.now()).date()


def effective_run_datetime(now: Optional[dt.datetime] = None) -> dt.datetime:
    day = effective_run_date(now)
    return dt.datetime.combine(day, dt.time.min)


def effective_publish_date(now: Optional[dt.datetime] = None) -> dt.date:
    """预报的**见刊日**，默认是覆盖窗口结束后的那个周一（run date + 7 天）。

    《万有预报》在次周周一发布，所以「还赶不赶得上」要按见刊日算，不能按窗口首日算：
    10.19–10.26 这一期在 10.26 早上见刊，10.20 截止的奖学金、10.23 结束的选课
    到那时都已经过期，留着只会误导读者。
    """
    parsed = _parse_override("WANYOU_PUBLISH_DATE")
    if parsed:
        return parsed
    return effective_run_date(now) + dt.timedelta(days=7)


def effective_publish_datetime(now: Optional[dt.datetime] = None) -> dt.datetime:
    return dt.datetime.combine(effective_publish_date(now), dt.time.min)
