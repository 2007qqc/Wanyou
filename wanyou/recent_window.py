"""「近一周」到底从哪一刻算起。

历史做法是滚动窗口 ``now - 7×24h``。它会在**任意时刻**截断，于是边界日白天
发出的推送会被整条丢掉。已复现：2026-11-02 12:39 那次运行截止在
10-26 12:39，把 10-26 11:50 发的《活动回顾&体验券免费领丨北体开放日专场》
漏了——而它明明还在「上一周」里。

现在的默认口径是**校历周对齐**：窗口从「本周一 00:00 往前 7 天」开始，也就是
「上一整个校历周 + 本周至今」。清华的校历周从周一开始（秋季学期第 1 周
2026-09-14 是周一），所以按自然周对齐就等于按校历周对齐，不需要联网查校历。

口径可切换（``config.WECHAT_RECENT_ALIGN`` / ``WECHAT_RECENT_ALIGN`` 环境变量）：

* ``week``（默认）—— 上一校历周周一 00:00 起
* ``day`` —— 今天 00:00 往前 ``days`` 天（整日覆盖）
* ``rolling`` —— 老的 ``now - days×24h``
"""

from __future__ import annotations

import datetime as dt
import os

import config

ALIGN_MODES = ("week", "day", "rolling")


def window_mode() -> str:
    raw = os.environ.get("WECHAT_RECENT_ALIGN") or getattr(config, "WECHAT_RECENT_ALIGN", "week")
    mode = str(raw or "week").strip().lower()
    return mode if mode in ALIGN_MODES else "week"


def window_start(days_limit=None, now=None) -> dt.datetime:
    days = int(float(days_limit or getattr(config, "WECHAT_MAIN_RECENT_DAYS", 7) or 7))
    days = max(days, 1)
    current = now or dt.datetime.now()
    mode = window_mode()

    if mode == "rolling":
        return current - dt.timedelta(days=days)

    midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
    if mode == "day":
        return midnight - dt.timedelta(days=days)

    # week：本周一 00:00 再往前 days 天
    monday = midnight - dt.timedelta(days=midnight.weekday())
    return monday - dt.timedelta(days=days)


def describe(start: dt.datetime, now=None) -> str:
    current = now or dt.datetime.now()
    labels = {"week": "校历周对齐", "day": "自然日对齐", "rolling": "滚动窗口"}
    label = labels.get(window_mode(), window_mode())
    return f"{start.strftime('%Y-%m-%d %H:%M')} → {current.strftime('%Y-%m-%d %H:%M')}（{label}）"
