import datetime as dt
import os
from typing import Optional


def effective_run_date(now: Optional[dt.datetime] = None) -> dt.date:
    override = os.environ.get("WANYOU_RUN_DATE", "").strip()
    if override:
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return dt.datetime.strptime(override, fmt).date()
            except ValueError:
                continue
    return (now or dt.datetime.now()).date()


def effective_run_datetime(now: Optional[dt.datetime] = None) -> dt.datetime:
    day = effective_run_date(now)
    return dt.datetime.combine(day, dt.time.min)
