"""公众号条目的「还赶不赶得上」判定。

背景：`temporal_filter` 只在解析出「截止/活动时间」时才会跟见刊日比较，解析不出来就一律
放行（`no_parseable_date_keep`）。公众号正文是微信读书给的节选，往往只有发布日期、没有
活动日期，于是整批过期内容都被放行了——时代论坛报名（10.22 发）、博物馆之夜（10.20 发）
就是这么混进来的。

所以公众号这条链路单独用更保守的规则，三道闸：

1. 回顾类关键词（回顾/落幕/圆满/名单公示…）直接判过期；
2. 正文里出现的最晚日期如果早于见刊日，判过期；
3. 剩下「一个日期都没有」的，交给 LLM 判断，**不确定就判过期**。
"""

import datetime as dt
import json
import re
from typing import Dict, List, Optional

import config
from wanyou.date_ranges import parse_dates, parse_deadline_dates
from wanyou.run_clock import effective_publish_datetime
from wanyou.temporal_filter import DATE_PATTERN, extract_temporal_signals
from wanyou.utils_dates import format_datetime_text
from wanyou.utils_llm import chat_complete

RETRO_HINTS = (
    "回顾", "落幕", "圆满", "顺利举行", "成功举办", "成功举行", "精彩瞬间",
    "赛况", "已结束", "名单公示", "公示", "顺利召开", "圆满结束", "收官",
    # 图片型推送常把「总结/纪实」写在标题里，正文只有几十字：不补这两个词，
    # 它们会走 image_only_keep 被当成待人工条目留下来（已复现两条）。
    "总结", "纪实",
)

_DATE_ONLY = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")


def _dates_in(text: str, year: int, reference: Optional[dt.date] = None) -> List[dt.datetime]:
    """日期解析走 wanyou/date_ranges：点分、区间、跨年都认。

    只认「11月7日」的老实现对「11.5」「11月7—8日」返回空，规则短路后交给 LLM，
    结果把未来日期判成过期（2026-11-02 无偿献血 11.7–11.8 被误杀）。
    """

    return [dt.datetime.combine(value, dt.time()) for value in parse_dates(text, year, reference)]


def _is_image_only(item: Dict[str, object]) -> bool:
    """正文极短但带图 —— 这类推送的信息基本都在图里。"""

    content = str(item.get("content") or "").strip()
    limit = int(getattr(config, "WECHAT_IMAGE_ONLY_MAX_CHARS", 120) or 120)
    if len(content) > limit:
        return False
    images = item.get("image_entries") or item.get("image_urls") or []
    return bool(images)


def _has_retro_hint(title: str) -> str:
    for hint in RETRO_HINTS:
        if hint in (title or ""):
            return hint
    return ""


def decide_item(item: Dict[str, object], publish_dt: Optional[dt.datetime] = None, use_llm: bool = True) -> Dict[str, object]:
    """返回 {keep, reason, evidence, source}。"""
    publish = publish_dt or effective_publish_datetime()
    title = str(item.get("title") or "")
    lede = str(item.get("lede") or "")
    summary = str(item.get("summary") or "")
    content = str(item.get("content") or "")
    # 标题/要点透视/摘要决定“是不是回顾类、有没有未来年份”；正文全文参与日期解析：
    # 现在能拿到整篇文章，活动时间、报名截止通常只在正文里。
    head_text = "\n".join(part for part in [title, lede, summary] if part)
    date_text = "\n".join(part for part in [head_text, content[:4000]] if part)

    hint = _has_retro_hint(title)
    if hint:
        return {"keep": False, "reason": f"retrospective:{hint}", "evidence": "", "source": "rule"}

    # 截止日期正好是见刊日（次周周一）的，不再保留：这天是报纸刊登日，截止时间
    # 在读者看到时已经进入最后时限。只针对“截止”类日期，不影响活动日期。
    signals = extract_temporal_signals(date_text, now=publish)
    deadlines = []
    for signal in signals:
        if signal.get("kind") != "deadline" or not signal.get("parsed"):
            continue
        try:
            deadlines.append(dt.datetime.fromisoformat(signal["parsed"]))
        except ValueError:
            continue
    if deadlines:
        latest_deadline = max(deadlines)
        if latest_deadline.date() == publish.date():
            return {
                "keep": False,
                "reason": "deadline_on_publish_day",
                "evidence": latest_deadline.strftime("%Y-%m-%d"),
                "source": "rule",
            }

    # 点分/区间的截止日期（「报名截止 11.8」）跑不进 extract_temporal_signals，
    # 这里再按「截止」行单独解析一遍，别让它们漏过截止日判断。
    for value in parse_deadline_dates(date_text, publish.year, publish.date()):
        if value == publish.date():
            return {
                "keep": False,
                "reason": "deadline_on_publish_day",
                "evidence": value.strftime("%Y-%m-%d"),
                "source": "rule",
            }

    # 标题里出现晚于见刊日所在年份的年份（如「2027年寒假课程项目」），必然是未来的事，
    # 直接放行，不要交给 LLM——实测同结构的三个项目推广，模型会给出不同答案。
    # 只看标题/要点透视/摘要，避免正文里顺带提到的年份造成误判。
    far_years = [int(year) for year in re.findall(r"(20\d{2})\s*年", head_text) if int(year) > publish.year]
    if far_years:
        return {
            "keep": True,
            "reason": "future_year_mentioned",
            "evidence": f"{max(far_years)}年",
            "source": "rule",
        }

    dates = _dates_in(date_text, publish.year, publish.date())
    future = [d for d in dates if d.date() >= (publish - dt.timedelta(hours=12)).date()]
    if dates and not future:
        latest = max(dates)
        return {
            "keep": False,
            "reason": "all_dates_before_publish",
            "evidence": latest.strftime("%Y-%m-%d"),
            "source": "rule",
        }
    if future:
        return {
            "keep": True,
            "reason": "future_date_found",
            "evidence": max(future).strftime("%Y-%m-%d"),
            "source": "rule",
        }

    # 图片型推送（正文只有几十字、信息全在图里）没有可解析日期，交给 LLM 只会得到
    # unknown 然后被丢掉。这类推送本来就是「海报 + 标题」，回顾类标题上面已经拦掉了，
    # 剩下的按「保留待人工」处理，比一律丢掉更有用。
    if _is_image_only(item) and getattr(config, "WECHAT_IMAGE_ONLY_KEEP", True):
        return {
            "keep": True,
            "reason": "image_only_keep",
            "evidence": "正文为图片，无可解析日期",
            "source": "rule",
        }

    if not use_llm:
        return {"keep": False, "reason": "no_date_no_check", "evidence": "", "source": "rule"}

    return _llm_judge(item, publish)


def _llm_judge(item: Dict[str, object], publish: dt.datetime) -> Dict[str, object]:
    prompt = (
        f"今天是 {publish:%Y-%m-%d}，这是《万有预报》的见刊日（读者在这一天才看到）。\n"
        "判断下面这条校园推送在见刊日之后是否仍然有效：活动还没办、报名还没截止、通知还在执行期内。\n"
        "只输出 JSON：{\"status\":\"valid|expired|unknown\",\"reason\":\"不超过 30 字\",\"date\":\"依据的日期，没有就空\"}\n"
        "判定规则：\n"
        "1) 标题或正文出现『回顾/落幕/公示/名单/已举办』→ expired；\n"
        "2) 正文给出的最晚日期早于见刊日 → expired；\n"
        "3) 报名/招募类，原文发布在见刊日 2 天以前、又没写报名截止时间 → expired"
        "（报名一般随活动结束；活动日期不明时按已过期处理）；\n"
        "4) 有明确晚于见刊日的活动日期 → valid；\n"
        "5) 信息不足以下结论 → unknown。宁可判 unknown，也不要猜 valid。"
    )
    user = (
        f"标题: {item.get('title', '')}\n"
        f"原推送发布: {format_datetime_text(item)}\n"
        f"要点透视: {item.get('lede', '')}\n"
        f"摘要: {item.get('summary', '')}\n"
        f"正文节选: {str(item.get('content') or '')[:1500]}"
    )
    raw = chat_complete(prompt, user, model=getattr(config, "WECHAT_SUMMARY_LLM_MODEL", "") or None, temperature=0, task_label=f"判定时效：{str(item.get('title', ''))[:18]}")
    if not raw:
        return {"keep": False, "reason": "llm_no_answer", "evidence": "", "source": "llm"}
    match = re.search(r"\{[\s\S]*\}", raw)
    try:
        data = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        data = {}
    status = str(data.get("status") or "unknown").strip().lower()
    return {
        "keep": status == "valid",
        "reason": f"llm:{status}:{str(data.get('reason') or '')[:40]}",
        "evidence": str(data.get("date") or ""),
        "source": "llm",
    }
