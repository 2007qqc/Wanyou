import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

import config
from wanyou.utils_llm import chat_complete


SECTION_OVERFLOW_KEEP_LIMITS = {
    "教务通知": 3,
    "家园网信息": 4,
    "图书馆信息": 4,
    "新清华学堂": 4,
    "物理系学术报告": 4,
    "学生会信息": 4,
    "青年科协信息": 4,
    "学生社团信息": 4,
    "学生公益信息": 4,
    "其他公众号信息": 4,
}

SECTION_OVERFLOW_TRIGGERS = {
    "教务通知": 5,
    "家园网信息": 6,
    "图书馆信息": 6,
    "新清华学堂": 6,
    "物理系学术报告": 6,
    "学生会信息": 6,
    "青年科协信息": 6,
    "学生社团信息": 6,
    "学生公益信息": 6,
    "其他公众号信息": 6,
}

SECTION_STALE_DAYS = {
    "教务通知": 10,
    "家园网信息": 10,
    "图书馆信息": 10,
    "新清华学堂": 14,
    "物理系学术报告": 21,
    "学生会信息": 10,
    "青年科协信息": 10,
    "学生社团信息": 10,
    "学生公益信息": 10,
    "其他公众号信息": 10,
}

SECTION_PRIORITY_KEYWORDS = {
    "教务通知": ["截止", "报名", "选课", "退课", "SRT", "奖学金", "课程", "考试", "学籍", "培养", "申请", "答辩", "交换", "国际", "C9"],
    "家园网信息": ["宿舍", "公寓", "教学楼", "放假", "门禁", "停水", "停电", "自习", "安全", "维修", "开放"],
    "图书馆信息": ["培训", "讲座", "数据库", "资源", "检索", "写作", "论文", "AI"],
    "新清华学堂": ["开票", "演出", "音乐会", "话剧", "歌剧", "购票", "优惠"],
    "物理系学术报告": ["报告", "讲座", "colloquium", "seminar", "speaker", "地点", "时间"],
    "学生会信息": ["权益", "反馈", "报名", "活动", "通知"],
    "青年科协信息": ["科创", "沙龙", "项目", "报名", "讲座", "创新"],
    "学生社团信息": ["招新", "报名", "活动", "社团"],
    "学生公益信息": ["志愿", "公益", "服务", "报名", "招募"],
    "其他公众号信息": ["截止", "报名", "讲座", "活动", "通知"],
}

COMMON_PRIORITY_KEYWORDS = [
    "截止", "报名", "申请", "时间", "地点", "对象", "通知", "讲座", "报告", "课程", "活动",
]
TIME_RELATED_LABELS = ["截止", "报名", "开票", "演出", "活动", "报告", "时间", "日期", "发布"]
SUMMARY_HARD_LIMIT = min(getattr(config, "LLM_SUMMARY_MAX_CHARS", 100), 80)
NOW = dt.datetime.now()
CURRENT_ISSUE_WEEK_START = (NOW - dt.timedelta(days=NOW.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def summarize_item(title: str, content: str, source: str = "", date: str = "") -> str:
    structured_summary = _structured_summary(content, source=source)
    if not getattr(config, "LLM_SUMMARY_ENABLED", False):
        return _finalize_summary(structured_summary or _fallback_summary(content), content)

    prompt = (
        f"标题: {title}\n"
        f"来源: {source}\n"
        f"日期: {date}\n"
        f"请压缩为不超过{SUMMARY_HARD_LIMIT}字、适合万有预报的简短中文摘要，优先保留时间、地点、截止、对象等核心信息。\n"
        f"正文:\n{content[:2000]}"
    )
    result = chat_complete(
        config.LLM_SUMMARY_SYSTEM_PROMPT,
        prompt,
        max_tokens=160,
        temperature=0.2,
        task_label=f"正在压缩单条信息篇幅：{title[:24]}",
    )
    if not result:
        return _finalize_summary(structured_summary or _fallback_summary(content), content)
    return _finalize_summary(result.strip()[:SUMMARY_HARD_LIMIT], content)



def generate_transition(section_name: str, summaries: Iterable[str], has_items: bool = False) -> str:
    summary_list = [item.strip() for item in summaries if item and item.strip()]
    if not getattr(config, "LLM_TRANSITION_ENABLED", False):
        return _fallback_transition(section_name, has_items)

    if not summary_list:
        prompt = f"栏目: {section_name}\n本周没有内容。"
    else:
        joined = "\n".join(f"- {item}" for item in summary_list[:5])
        prompt = f"栏目: {section_name}\n要点:\n{joined}"

    result = chat_complete(
        config.LLM_TRANSITION_SYSTEM_PROMPT,
        prompt,
        max_tokens=80,
        temperature=0.4,
        task_label=f"正在生成栏目导语：{section_name}",
    )
    if not result:
        return _fallback_transition(section_name, has_items)
    return result.strip()



def enrich_markdown_section(section_name: str, items: List[dict]) -> List[dict]:
    selected_items = _select_section_items(section_name, items)
    enriched = []
    for item in selected_items:
        copied = dict(item)
        copied["summary"] = summarize_item(
            copied.get("title", ""),
            copied.get("content", ""),
            source=copied.get("source", ""),
            date=copied.get("date", ""),
        )
        enriched.append(copied)
    return enriched



def parse_markdown_document(markdown_text: str) -> List[dict]:
    sections = []
    current_section = None
    current_item = None

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("# "):
            if current_item and current_section is not None:
                current_section["items"].append(current_item)
                current_item = None
            if current_section is not None:
                sections.append(current_section)
            current_section = {"title": line[2:].strip(), "items": []}
            continue

        if line.startswith("## "):
            if current_section is None:
                current_section = {"title": "未分类", "items": []}
            if current_item is not None:
                current_section["items"].append(current_item)
            current_item = {"title": line[3:].strip(), "body_lines": []}
            continue

        if current_item is not None:
            current_item["body_lines"].append(raw_line)

    if current_item and current_section is not None:
        current_section["items"].append(current_item)
    if current_section is not None:
        sections.append(current_section)

    return sections



def build_augmented_markdown(markdown_text: str, current_markdown_path: str = "") -> str:
    rendered_sections = []
    previous_report_index = _load_previous_report_index(current_markdown_path)
    for section in parse_markdown_document(markdown_text):
        items = []
        for item in section["items"]:
            body = "\n".join(item["body_lines"]).strip()
            items.append(
                {
                    "title": item["title"],
                    "content": body,
                    "source": section["title"],
                    "date": _extract_inline_date(body),
                }
            )
        items = _prefilter_section_items(section["title"], items, previous_report_index)
        enriched = enrich_markdown_section(section["title"], items)
        transition = generate_transition(
            section["title"],
            [item.get("summary", "") for item in enriched],
            has_items=bool(enriched),
        )

        parts = [f"# {section['title']}", "", transition, ""]
        for item in enriched:
            parts.append(f"## {item['title']}")
            parts.append("")
            if item.get("summary"):
                parts.append(f"\u8981\u70b9\u900f\u89c6\uff1a{item['summary']}")
                parts.append("")
            content = item.get("content", "").strip()
            if content:
                parts.append(content)
                parts.append("")
        rendered_sections.append("\n".join(parts).strip())

    return "\n\n".join(section for section in rendered_sections if section).strip() + "\n"


def _prefilter_section_items(section_name: str, items: List[dict], previous_report_index: Dict[str, Set[str]]) -> List[dict]:
    filtered = []
    previous_titles = previous_report_index.get(section_name, set())
    for item in items:
        if _was_in_previous_report(item, previous_titles):
            continue
        temporal = _resolve_item_temporal_by_rules(section_name, item)
        if _should_skip_for_current_issue(temporal):
            continue
        copied = dict(item)
        copied["prefilter_temporal"] = temporal
        filtered.append(copied)
    return filtered



def _load_previous_report_index(current_markdown_path: str) -> Dict[str, Set[str]]:
    output_dir = os.path.abspath(getattr(config, "OUTPUT_DIR", "./output"))
    if not os.path.isdir(output_dir):
        return {}

    current_abs = os.path.abspath(current_markdown_path) if current_markdown_path else ""
    current_ts = _extract_report_timestamp_from_path(current_abs)
    prefix = f"{getattr(config, 'OUTPUT_NAME_PREFIX', 'wanyou')}_"
    candidates = []
    for root, _, files in os.walk(output_dir):
        for name in files:
            if not name.startswith(prefix):
                continue
            if not name.endswith('.md') or name.endswith('_raw.md'):
                continue
            full_path = os.path.abspath(os.path.join(root, name))
            if current_abs and full_path == current_abs:
                continue
            report_ts = _extract_report_timestamp_from_path(full_path)
            if report_ts is None:
                continue
            candidates.append((report_ts, full_path))

    if not candidates:
        return {}

    candidates.sort(key=lambda pair: (pair[0], pair[1]), reverse=True)
    chosen_path = ""
    if current_ts is not None:
        for report_ts, candidate_path in candidates:
            if report_ts < current_ts:
                chosen_path = candidate_path
                break
    if not chosen_path:
        chosen_path = candidates[0][1]

    try:
        previous_text = Path(chosen_path).read_text(encoding='utf-8')
    except Exception:
        return {}

    index: Dict[str, Set[str]] = {}
    for section in parse_markdown_document(previous_text):
        title_set = {_normalize_title_key(item.get('title', '')) for item in section.get('items', [])}
        title_set = {title for title in title_set if title}
        if title_set:
            index[section['title']] = title_set
    return index



def _extract_report_timestamp_from_path(path_text: str) -> Optional[dt.datetime]:
    basename = os.path.basename(path_text or "")
    match = re.match(rf"{re.escape(getattr(config, 'OUTPUT_NAME_PREFIX', 'wanyou'))}_(\d{{8}}_\d{{4}})(?:_raw)?\.md$", basename)
    if not match:
        return None
    try:
        return dt.datetime.strptime(match.group(1), "%Y%m%d_%H%M")
    except Exception:
        return None


def _normalize_title_key(title: str) -> str:
    cleaned = re.sub(r"\s+", "", title or "")
    cleaned = re.sub(r"[??\[\]()??,??:??|?/\\-]", "", cleaned)
    return cleaned.lower().strip()



def _was_in_previous_report(item: dict, previous_titles: Set[str]) -> bool:
    title_key = _normalize_title_key(item.get('title', ''))
    if not title_key or not previous_titles:
        return False
    return title_key in previous_titles



def _should_skip_for_current_issue(temporal: dict) -> bool:
    relevant_dt = temporal.get('relevant_dt')
    kind = temporal.get('kind') or 'unknown'
    if temporal.get('is_expired'):
        return True
    if relevant_dt is None:
        return False
    if kind in {'deadline', 'event', 'publish'}:
        return relevant_dt < CURRENT_ISSUE_WEEK_START
    return False


def _select_section_items(section_name: str, items: List[dict]) -> List[dict]:
    active_items = []
    for item in items:
        temporal = _resolve_item_temporal(section_name, item)
        copied = dict(item)
        copied["temporal"] = temporal
        if not temporal.get("is_expired"):
            active_items.append(copied)

    if not active_items:
        return []

    active_items.sort(key=_sort_key_for_item, reverse=True)
    keep_limit = SECTION_OVERFLOW_KEEP_LIMITS.get(section_name, 0)
    overflow_trigger = SECTION_OVERFLOW_TRIGGERS.get(section_name, max(keep_limit + 2, 6) if keep_limit else 0)
    if not keep_limit or not overflow_trigger or len(active_items) <= overflow_trigger:
        return active_items

    selected_indexes = _select_items_with_llm(section_name, active_items, keep_limit)
    if not selected_indexes:
        selected_indexes = _select_items_with_rules(section_name, active_items, keep_limit)

    selected_indexes = sorted(index for index in selected_indexes if 0 <= index < len(active_items))
    if not selected_indexes:
        return active_items[:keep_limit]
    selected = [active_items[index] for index in selected_indexes]
    selected.sort(key=_sort_key_for_item, reverse=True)
    return selected



def _resolve_item_temporal(section_name: str, item: dict) -> dict:
    heuristic = dict(item.get("prefilter_temporal") or _resolve_item_temporal_by_rules(section_name, item))
    text = f"{item.get('title', '')}\n{item.get('content', '')}"
    if heuristic.get("certainty") == "high":
        return heuristic
    if not _looks_time_sensitive_text(text):
        return heuristic
    llm_meta = _resolve_item_temporal_with_llm(section_name, item)
    if not llm_meta:
        return heuristic
    if llm_meta.get("confidence") == "high" or heuristic.get("certainty") != "high":
        return llm_meta
    return heuristic



def _resolve_item_temporal_by_rules(section_name: str, item: dict) -> dict:
    text = f"{item.get('title', '')}\n{item.get('content', '')}"
    stale_days = SECTION_STALE_DAYS.get(section_name, 10)
    publish_dt = _parse_first_datetime(text, ["发布日期", "发布时间", "日期"])
    deadline_dt = _parse_first_datetime(text, ["报名截止", "截止时间", "截止日期", "截止"])
    event_dt = _parse_first_datetime(text, ["报告时间", "演出时间", "活动时间", "开票时间", "时间"])

    relevant_dt = deadline_dt or event_dt or publish_dt
    kind = "deadline" if deadline_dt else "event" if event_dt else "publish" if publish_dt else "unknown"
    is_expired = False
    certainty = "medium" if relevant_dt else "low"

    if deadline_dt:
        is_expired = deadline_dt < NOW
        certainty = "high"
    elif event_dt:
        is_expired = event_dt < NOW - dt.timedelta(hours=12)
        certainty = "high"
    elif publish_dt:
        is_expired = publish_dt < NOW - dt.timedelta(days=stale_days)
    else:
        inline_date = _extract_inline_date(text)
        if inline_date:
            parsed = _parse_date_like(inline_date)
            if parsed is not None:
                relevant_dt = parsed
                is_expired = parsed < NOW - dt.timedelta(days=stale_days)
                kind = "publish"
                certainty = "medium"

    return {
        "kind": kind,
        "relevant_dt": relevant_dt,
        "sort_ts": relevant_dt.timestamp() if relevant_dt else 0,
        "is_expired": bool(is_expired),
        "certainty": certainty,
    }



def _resolve_item_temporal_with_llm(section_name: str, item: dict) -> Optional[dict]:
    title = (item.get("title") or "").strip()
    content = (item.get("content") or "").strip()
    system_prompt = (
        "你要判断一条通知在本期万有预报中是否已经过时。"
        "请阅读标题和正文，提取最相关的日期/时间，并与当前制作时间比较。"
        "优先识别截止时间、活动开始时间、报告时间、开票时间；若没有，再看发布日期。"
        "只输出 JSON，格式为 {\"kind\":\"deadline|event|publish|unknown\",\"relevant_date\":\"YYYY-MM-DD\",\"relevant_time\":\"HH:MM\",\"is_expired\":true|false,\"confidence\":\"low|medium|high\"}。"
    )
    user_prompt = (
        f"当前万有预报制作时间: {NOW.strftime('%Y-%m-%d %H:%M')}\n"
        f"栏目: {section_name}\n"
        f"标题: {title}\n"
        f"正文:\n{content[:2200]}"
    )
    result = chat_complete(
        system_prompt,
        user_prompt,
        max_tokens=180,
        temperature=0,
        task_label=f"正在判断{section_name}条目时效：{title[:24]}",
    )
    if not result:
        return None
    match = re.search(r"\{[\s\S]*\}", result)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except Exception:
        return None

    relevant_dt = _parse_date_and_time_like(
        str(payload.get("relevant_date") or "").strip(),
        str(payload.get("relevant_time") or "").strip(),
    )
    return {
        "kind": str(payload.get("kind") or "unknown").strip(),
        "relevant_dt": relevant_dt,
        "sort_ts": relevant_dt.timestamp() if relevant_dt else 0,
        "is_expired": bool(payload.get("is_expired", False)),
        "certainty": str(payload.get("confidence") or "medium").strip().lower() or "medium",
        "confidence": str(payload.get("confidence") or "medium").strip().lower() or "medium",
    }



def _looks_time_sensitive_text(text: str) -> bool:
    compact = text or ""
    if re.search(r"20\d{2}[年\-/.]\d{1,2}[月\-/.]\d{1,2}", compact):
        return True
    if re.search(r"\d{1,2}[:：]\d{2}", compact):
        return True
    return any(keyword in compact for keyword in TIME_RELATED_LABELS)



def _parse_first_datetime(text: str, labels: List[str]) -> Optional[dt.datetime]:
    for label in labels:
        pattern = rf"{re.escape(label)}[：:]\s*([^\n]+)"
        match = re.search(pattern, text)
        if not match:
            continue
        parsed = _parse_date_and_time_from_text(match.group(1).strip())
        if parsed is not None:
            return parsed
    return None



def _parse_date_and_time_from_text(text: str) -> Optional[dt.datetime]:
    date_match = re.search(r"(20\d{2})[年\-/.](\d{1,2})[月\-/.](\d{1,2})", text)
    if not date_match:
        return None
    hour = 23
    minute = 59
    time_match = re.search(r"(\d{1,2})[:：](\d{2})", text)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
    try:
        return dt.datetime(
            int(date_match.group(1)),
            int(date_match.group(2)),
            int(date_match.group(3)),
            hour,
            minute,
        )
    except Exception:
        return None



def _parse_date_and_time_like(date_text: str, time_text: str) -> Optional[dt.datetime]:
    parsed_date = _parse_date_like(date_text)
    if parsed_date is None:
        return None
    if time_text and re.fullmatch(r"\d{1,2}:\d{2}", time_text):
        hour, minute = time_text.split(":")
        try:
            hour_value = int(hour)
            minute_value = int(minute)
        except Exception:
            hour_value = 23
            minute_value = 59
        if hour_value == 24 and minute_value == 0:
            return parsed_date.replace(hour=23, minute=59) + dt.timedelta(minutes=1)
        hour_value = min(max(hour_value, 0), 23)
        minute_value = min(max(minute_value, 0), 59)
        return parsed_date.replace(hour=hour_value, minute=minute_value)
    return parsed_date.replace(hour=23, minute=59)



def _parse_date_like(text: str) -> Optional[dt.datetime]:
    match = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", text)
    if not match:
        match = re.search(r"(20\d{2})[年\-/.](\d{1,2})[月\-/.](\d{1,2})", text)
    if not match:
        return None
    try:
        return dt.datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), 23, 59)
    except Exception:
        return None



def _sort_key_for_item(item: dict):
    temporal = item.get("temporal") or {}
    relevant_dt = temporal.get("relevant_dt")
    freshness = relevant_dt.timestamp() if relevant_dt else 0
    return (_importance_score(item.get("source", ""), item), freshness)



def _select_items_with_llm(section_name: str, items: List[dict], limit: int) -> List[int]:
    if not getattr(config, "LLM_ENABLED", False):
        return []

    candidates = []
    for index, item in enumerate(items, start=1):
        title = (item.get("title") or "").strip()
        snippet = _clean_summary_text(item.get("content", ""))[:160]
        temporal = item.get("temporal") or {}
        relevant_dt = temporal.get("relevant_dt")
        date_text = relevant_dt.strftime("%Y-%m-%d %H:%M") if relevant_dt else (item.get("date") or "")
        candidates.append(f"{index}. 标题: {title}\n   相关时间: {date_text}\n   摘要: {snippet}")

    system_prompt = (
        "你正在为清华大学物理系同学筛选每周信息简报。"
        "请优先保留未过时、时间更近、对物理系同学更刚需的条目。"
        "若信息很多，优先保留截止临近、报名申请、课程考试、宿舍教学楼安排、重要讲座报告。"
        "只输出 JSON，格式为 {\"keep_indices\": [1,2,3]}。"
    )
    user_prompt = (
        f"当前制作时间: {NOW.strftime('%Y-%m-%d %H:%M')}\n"
        f"栏目: {section_name}\n"
        f"最多保留: {limit} 条\n\n"
        + "\n\n".join(candidates[:12])
    )
    result = chat_complete(
        system_prompt,
        user_prompt,
        max_tokens=160,
        temperature=0,
        task_label=f"正在筛选{section_name}重点条目",
    )
    if not result:
        return []

    match = re.search(r"\{[\s\S]*\}", result)
    if not match:
        return []
    try:
        payload = json.loads(match.group(0))
    except Exception:
        return []

    indices = payload.get("keep_indices") or []
    cleaned = []
    for value in indices:
        try:
            idx = int(value) - 1
        except Exception:
            continue
        if idx not in cleaned:
            cleaned.append(idx)
    return cleaned[:limit]



def _select_items_with_rules(section_name: str, items: List[dict], limit: int) -> List[int]:
    scored = []
    for index, item in enumerate(items):
        score = _importance_score(section_name, item)
        freshness = (item.get("temporal") or {}).get("sort_ts", 0)
        scored.append((score, freshness, index))
    scored.sort(key=lambda pair: (-pair[0], -pair[1], pair[2]))
    chosen = sorted(index for _, _, index in scored[:limit])
    return chosen



def _importance_score(section_name: str, item: dict) -> int:
    title = (item.get("title") or "").strip()
    content = (item.get("content") or "").strip()
    text = f"{title}\n{content}"
    lowered = text.lower()
    score = 0

    if "占位卡片" in title or "本次抓取未成功" in text:
        return -100

    temporal = item.get("temporal") or {}
    relevant_dt = temporal.get("relevant_dt")
    if relevant_dt:
        delta_days = (relevant_dt - NOW).total_seconds() / 86400
        if -1 <= delta_days <= 7:
            score += 10
        elif 7 < delta_days <= 14:
            score += 5
        elif delta_days < -1:
            score -= 8

    for keyword in COMMON_PRIORITY_KEYWORDS:
        if keyword.lower() in lowered:
            score += 2
    for keyword in SECTION_PRIORITY_KEYWORDS.get(section_name, []):
        if keyword.lower() in lowered:
            score += 4

    if re.search(r"截止|最后|尽快|立即|本周内|本周", text):
        score += 6
    if re.search(r"报名|申请|注册|选课|退课|开票", text):
        score += 5
    if re.search(r"时间|地点|对象|方式|链接", text):
        score += 2
    if len(re.findall(r"\d{4}-\d{2}-\d{2}|\d{1,2}[:：]\d{2}", text)):
        score += 2
    if len(title) <= 38:
        score += 1
    return score



def _extract_inline_date(text: str) -> str:
    content = text or ""
    match = re.search(r"(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2})", content)
    if not match:
        return ""
    value = match.group(1).replace("年", "-").replace("月", "-").replace("日", "")
    value = value.replace("/", "-").replace(".", "-")
    parts = [part for part in value.split("-") if part]
    if len(parts) >= 3:
        return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
    return value



def _fallback_summary(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return ""

    paragraphs = _extract_candidate_paragraphs(text)
    for paragraph in paragraphs:
        if _is_metadata_paragraph(paragraph):
            continue
        cleaned = _clean_summary_text(paragraph)
        if cleaned:
            return _clip_summary(cleaned)

    compact = _clean_summary_text(" ".join(text.split()))
    return compact[:SUMMARY_HARD_LIMIT]



def _structured_summary(content: str, source: str = "") -> str:
    text = (content or "").strip()
    if not text:
        return ""

    explicit_summary = _extract_labeled_value(text, "报告摘要")
    if explicit_summary:
        return _clip_summary(explicit_summary)

    explicit_summary = _extract_labeled_value(text, "摘要")
    if explicit_summary:
        return _clip_summary(explicit_summary)

    for paragraph in _extract_candidate_paragraphs(text):
        if _is_metadata_paragraph(paragraph):
            continue
        cleaned = _clean_summary_text(paragraph)
        if cleaned:
            return _clip_summary(cleaned)

    return ""



def _extract_labeled_value(text: str, label: str) -> str:
    pattern = rf"{re.escape(label)}[：:]\s*(.+)"
    match = re.search(pattern, text, flags=re.S)
    if not match:
        return ""
    value = match.group(1).strip()
    value = re.split(r"\n(?:[A-Za-z\u4e00-\u9fff ]{1,12})[：:]", value, maxsplit=1)[0].strip()
    return value



def _clip_summary(text: str) -> str:
    compact = " ".join((text or "").split())
    return compact[:SUMMARY_HARD_LIMIT]



def _finalize_summary(summary: str, content: str = "") -> str:
    cleaned_summary = _clip_summary(summary)
    if cleaned_summary and _looks_like_complete_summary(cleaned_summary):
        if not _is_summary_redundant(cleaned_summary, content):
            return cleaned_summary
    return ""



def _extract_candidate_paragraphs(text: str) -> List[str]:
    normalized = text.replace("\r\n", "\n")
    blocks = [block.strip() for block in re.split(r"\n\s*\n", normalized) if block.strip()]
    candidates = []
    for block in blocks:
        cleaned = _strip_leading_metadata(_clean_summary_text(block))
        if cleaned:
            candidates.append(cleaned)
    return candidates



def _clean_summary_text(text: str) -> str:
    cleaned = text or ""
    cleaned = re.sub(r"!\[[^\]]*]\([^)]*\)", " ", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\(([^)]*)\)", r"\1", cleaned)
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = re.sub(r"\[\s*]", " ", cleaned)
    cleaned = re.sub(r"[*_#>`-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ：|")



def _is_metadata_paragraph(text: str) -> bool:
    compact = _clean_summary_text(text)
    if not compact:
        return True

    metadata_label_pattern = (
        r"^(?:日期|时间|地点|链接|票价|报告人|报告时间|报告地点|发布日期|地点提示|主讲|嘉宾|来源|浏览|点击|作者)[：:]"
    )
    if all(
        re.match(metadata_label_pattern, part.strip()) or not re.search(r"[\u4e00-\u9fffA-Za-z]", part)
        for part in re.split(r"[：:|]", compact)
    ):
        return True

    if re.fullmatch(r"(日期|时间|地点|链接|票价|报告人|主讲|嘉宾|发布(?:日期)?)[：:].*", compact):
        return True

    if compact.startswith("http"):
        return True

    meaningful_chinese = len(re.findall(r"[\u4e00-\u9fff]", compact))
    sentence_punct = len(re.findall(r"[。！？；]", compact))

    if meaningful_chinese < 8 and sentence_punct == 0:
        return True

    return False



def _looks_like_complete_summary(text: str) -> bool:
    compact = _clean_summary_text(text)
    if not compact or _is_metadata_paragraph(compact):
        return False

    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", compact))
    latin_words = len(re.findall(r"[A-Za-z]{4,}", compact))
    has_sentence_shape = bool(re.search(r"[。！？；]", compact)) or chinese_chars >= 20 or latin_words >= 8
    return has_sentence_shape



def _is_summary_redundant(summary: str, content: str) -> bool:
    summary_norm = _normalize_compare_text(summary)
    if not summary_norm:
        return True

    paragraphs = _extract_candidate_paragraphs(content or "")
    if not paragraphs:
        return False

    for paragraph in paragraphs[:3]:
        paragraph_norm = _normalize_compare_text(paragraph)
        if not paragraph_norm:
            continue
        if summary_norm == paragraph_norm:
            return True
        if summary_norm in paragraph_norm or paragraph_norm in summary_norm:
            return True
        if _token_overlap_ratio(summary_norm, paragraph_norm) >= 0.88:
            return True

    return False



def _normalize_compare_text(text: str) -> str:
    cleaned = _clean_summary_text(text)
    cleaned = re.sub(r"[，。！？；、：:（）()\[\]“”\"'《》>·\-/\\]", "", cleaned)
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned.strip().lower()



def _token_overlap_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    left_tokens = _compare_tokens(left)
    right_tokens = _compare_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    base = min(len(left_tokens), len(right_tokens))
    return overlap / base if base else 0.0



def _compare_tokens(text: str) -> set[str]:
    cjk_bigrams = {text[i : i + 2] for i in range(len(text) - 1)} if len(text) > 1 else {text}
    latin_words = set(re.findall(r"[a-z0-9]{3,}", text))
    return {token for token in cjk_bigrams | latin_words if token}



def _strip_leading_metadata(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""

    patterns = [
        r"^(?:日期|时间|地点|链接|票价|报告人|报告时间|报告地点|发布日期|主讲|嘉宾|来源)[：:][^。！？；]*",
        r"^(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(?:\s+\d{1,2}[:：]\d{2})?)",
        r"^(?:\*+\s*)?(?:前两排|校内|校友|学生特惠|优惠|折扣)[^。！？；]*",
    ]

    changed = True
    while changed and cleaned:
        changed = False
        for pattern in patterns:
            new_text = re.sub(pattern, "", cleaned).lstrip(" ：|")
            if new_text != cleaned:
                cleaned = new_text
                changed = True

    return cleaned.strip()



def _fallback_transition(section_name: str, has_content: bool) -> str:
    defaults = getattr(config, "SECTION_DEFAULT_TRANSITIONS", {})
    if not has_content:
        return defaults.get("EMPTY", "本周暂无相关信息。")
    return defaults.get(section_name, "下面来看看本周值得关注的内容。")
