"""当前校历周次（教学周）的获取。

优先级按产品要求：**实时从 info 门户拿**，拿不到就不输出周数，绝不拿本地推算顶替。

为什么不去读校历图片：校历在 info 上是一张 6690×7294 的整年大图，视觉模型
（glm-4v-flash）在实测中把第 8 周读成第 4 周；错一个数字比不写更糟。

所以这里用的是 info 教务通知自带的口径：通知标题写「第N周（周五）」，正文写
「日期：2026年10月23日」。两者一配就是一组精确锚点——第 N 周的那个周五是哪天。
拿到锚点后，用纯日期运算就能得到今天属于第几周，不依赖任何模型判断。

抓不到（未登录、列表没有带周次的条目、网络不通）一律返回 ``None``。
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
import time
from typing import List, Optional, Tuple

import config

# 「第6周（周五）」/「第 6 周(周五)」/「第6周（星期5）」都能认
_WEEK_TITLE_RE = re.compile(r"第\s*([0-9]{1,2})\s*周\s*[（(]\s*(?:周|星期)\s*([一二三四五六日天0-9])\s*[)）]")
_DATE_RE = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_WEEKDAYS = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}

CACHE_PATH = os.path.join("output", ".cache", "academic_week.json")


def _weekday_index(token: str) -> Optional[int]:
    if token.isdigit():
        value = int(token)
        # 「星期5」是周五
        return value - 1 if 1 <= value <= 7 else None
    return _WEEKDAYS.get(token)


def week_from_anchor(anchor_week: int, anchor_date: _dt.date, weekday_token: str, today: _dt.date) -> int:
    """已知「第 anchor_week 周的周X 是 anchor_date」，求 today 所在教学周。"""

    index = _weekday_index(weekday_token)
    if index is None:
        raise ValueError(f"unrecognized weekday: {weekday_token!r}")
    anchor_monday = anchor_date - _dt.timedelta(days=index)
    today_monday = today - _dt.timedelta(days=today.weekday())
    return anchor_week + round((today_monday - anchor_monday).days / 7)


def semester_label(today: _dt.date) -> str:
    """2026 年 11 月 → 2026-2027学年秋季学期。"""

    if today.month >= 8:
        return f"{today.year}-{today.year + 1}学年秋季学期"
    if today.month == 1:
        return f"{today.year - 1}-{today.year}学年秋季学期"
    return f"{today.year - 1}-{today.year}学年春季学期"


def _parse_anchors(title: str, body: str) -> Optional[Tuple[int, _dt.date, str]]:
    title_match = _WEEK_TITLE_RE.search(title or "")
    if not title_match:
        return None
    week = int(title_match.group(1))
    token = title_match.group(2)
    wanted = _weekday_index(token)

    candidates: List[_dt.date] = []
    for y, m, d in _DATE_RE.findall(body or ""):
        try:
            candidates.append(_dt.date(int(y), int(m), int(d)))
        except ValueError:
            continue
    if not candidates:
        return None
    if wanted is not None:
        for candidate in candidates:
            if candidate.weekday() == wanted:
                return week, candidate, title_match.group(0)
    return week, candidates[0], title_match.group(0)


def _cache_read(today: _dt.date) -> Optional[dict]:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return None
    if str(payload.get("date")) != today.isoformat():
        return None
    week = payload.get("week")
    if not isinstance(week, int) or not 1 <= week <= 30:
        return None
    return payload


def _cache_write(payload: dict) -> None:
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    except Exception:
        pass


def fetch_current_week(today: Optional[_dt.date] = None, *, allow_cache: bool = True) -> Optional[dict]:
    """登录 info 门户，从教务通知的「第N周（周X）+ 日期」反推本周教学周。

    任何一步失败都返回 ``None``——调用方据此决定不输出周数。
    """

    today = today or _dt.date.today()
    # 显式关掉时连缓存都不读：调用方要的是「这次就别写周数」
    if str(os.environ.get("WANYOU_ACADEMIC_WEEK", "auto")).strip().lower() in {"0", "off", "false", "no"}:
        return None
    if allow_cache:
        cached = _cache_read(today)
        if cached:
            return cached

    username = os.environ.get("WANYOU_USERNAME", "").strip()
    password = os.environ.get("WANYOU_PASSWORD", "").strip()
    if not username or not password:
        return None

    browser = None
    try:
        from wanyou.crawlers_info import _info_url_with_lmid
        from wanyou.unified_auth import authenticate_shared_browser

        debug_dir = os.path.join("output", ".cache", "academic_week_debug")
        browser = authenticate_shared_browser(
            username, password, debug_dir, config.URL_INFO, stage_label="校历周次",
        )
        browser.get(_info_url_with_lmid(config.URL_INFO, "LM_JWGG"))
        time.sleep(2)

        anchors = browser.execute_script("""
            return Array.prototype.slice.call(document.querySelectorAll('a'))
                .map(function (a) { return {text: (a.innerText || '').trim(), href: a.href}; })
                .filter(function (o) { return /第\\s*[0-9]{1,2}\\s*周\\s*[（(]/.test(o.text) && o.href; });
        """) or []
        if not anchors:
            browser.get(config.URL_INFO)
            time.sleep(2)
            anchors = browser.execute_script("""
                return Array.prototype.slice.call(document.querySelectorAll('a'))
                    .map(function (a) { return {text: (a.innerText || '').trim(), href: a.href}; })
                    .filter(function (o) { return /第\\s*[0-9]{1,2}\\s*周\\s*[（(]/.test(o.text) && o.href; });
            """) or []
        if not anchors:
            return None

        for anchor in anchors[:6]:
            title = anchor["text"]
            try:
                browser.get(anchor["href"])
                time.sleep(1.5)
            except Exception:
                continue
            body = browser.execute_script("return document.body ? document.body.innerText : ''") or ""
            parsed = _parse_anchors(title, body)
            if not parsed:
                continue
            anchor_week, anchor_date, matched = parsed
            week = week_from_anchor(anchor_week, anchor_date, _WEEK_TITLE_RE.search(title).group(2), today)
            if not 1 <= week <= 30:
                continue
            payload = {
                "date": today.isoformat(),
                "week": week,
                "semester": semester_label(today),
                "anchor": matched,
                "anchor_date": anchor_date.isoformat(),
                "source": "info",
            }
            _cache_write(payload)
            return payload
        return None
    except Exception as exc:  # 登录失败、网络不通、页面改版都走这里
        print(f"[week] 从 info 取校历周次失败，本期不输出周数：{type(exc).__name__}: {exc}", file=sys.stderr)
        return None
    finally:
        if browser is not None:
            try:
                browser.quit()
            except Exception:
                pass


def summary_line(today: Optional[_dt.date] = None, now: Optional[_dt.datetime] = None) -> str:
    """页头那行元信息：生成时间 +（拿得到时）校历周次。"""

    now = now or _dt.datetime.now()
    today = today or now.date()
    stamp = f"{now.year}年{now.month}月{now.day}日 {now.hour:02d}:{now.minute:02d} 生成"
    info = fetch_current_week(today)
    if not info:
        return stamp
    return f"{stamp} · {info['semester']}第{info['week']}周"
