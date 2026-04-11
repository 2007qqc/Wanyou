import datetime as dt
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

import config
from wanyou.utils_llm import chat_complete


MAX_ITEMS_PER_SECTION = 4
WECHAT_MAX_ITEMS = 5
SUMMARY_HARD_LIMIT = 70
ITEM_TOTAL_UNIT_LIMIT = 250
NOW = dt.datetime.now()
PHYSICS_SECTION = "物理系学术报告"


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
        section_name = section["title"]
        items = []
        for item in section["items"]:
            body = "\n".join(item["body_lines"]).strip()
            items.append(
                {
                    "title": item["title"],
                    "content": body,
                    "source": section_name,
                    "date": _extract_inline_date(body),
                }
            )

        items = _remove_previous_issue_items(section_name, items, previous_report_index)
        items = _filter_section_items(section_name, items)
        enriched = _enrich_items(section_name, items)
        transition = _generate_transition(section_name, [item.get("summary", "") for item in enriched], bool(enriched))

        parts = [f"# {section_name}", "", transition, ""]
        for item in enriched:
            parts.append(f"## {item['title']}")
            parts.append("")
            if item.get("summary"):
                parts.append(f"要点透视：{item['summary']}")
                parts.append("")
            if item.get("content"):
                parts.append(item["content"])
                parts.append("")
        rendered_sections.append("\n".join(parts).strip())

    return "\n\n".join(section for section in rendered_sections if section).strip() + "\n"


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
            if not name.startswith(prefix) or not name.endswith(".md") or name.endswith("_raw.md"):
                continue
            full_path = os.path.abspath(os.path.join(root, name))
            if current_abs and full_path == current_abs:
                continue
            report_ts = _extract_report_timestamp_from_path(full_path)
            if report_ts is not None:
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
        previous_text = Path(chosen_path).read_text(encoding="utf-8")
    except Exception:
        return {}

    index: Dict[str, Set[str]] = {}
    for section in parse_markdown_document(previous_text):
        title_set = {_normalize_title_key(item.get("title", "")) for item in section.get("items", [])}
        title_set = {title for title in title_set if title}
        if title_set:
            index[section["title"]] = title_set
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
    cleaned = re.sub(r"[\[\](){}，,：:|?/\\\-]", "", cleaned)
    return cleaned.lower().strip()


def _remove_previous_issue_items(section_name: str, items: List[dict], previous_report_index: Dict[str, Set[str]]) -> List[dict]:
    previous_titles = previous_report_index.get(section_name, set())
    if not previous_titles:
        return items
    filtered = []
    for item in items:
        if _normalize_title_key(item.get("title", "")) in previous_titles:
            continue
        filtered.append(item)
    return filtered


def _filter_section_items(section_name: str, items: List[dict]) -> List[dict]:
    if not items:
        return []

    if section_name == PHYSICS_SECTION:
        items = [item for item in items if not _physics_item_is_expired(item)]
        items.sort(key=lambda item: _extract_inline_datetime(item.get("content", "")) or dt.datetime.min, reverse=True)
        return items[:MAX_ITEMS_PER_SECTION]

    if section_name == "其他公众号信息":
        return items[:WECHAT_MAX_ITEMS]

    if len(items) <= MAX_ITEMS_PER_SECTION:
        return items

    selected = _select_items_with_llm(section_name, items, MAX_ITEMS_PER_SECTION)
    if selected:
        return selected
    return items[:MAX_ITEMS_PER_SECTION]


def _physics_item_is_expired(item: dict) -> bool:
    content = item.get("content", "")
    event_dt = _extract_labeled_datetime(content, ["报告时间", "时间", "活动时间"])
    if event_dt is None:
        return False
    return event_dt < NOW - dt.timedelta(hours=12)


def _extract_labeled_datetime(text: str, labels: List[str]) -> Optional[dt.datetime]:
    for label in labels:
        match = re.search(rf"{re.escape(label)}[：:]\s*([^\n]+)", text or "")
        if not match:
            continue
        parsed = _parse_datetime_text(match.group(1).strip())
        if parsed is not None:
            return parsed
    return None


def _extract_inline_datetime(text: str) -> Optional[dt.datetime]:
    match = re.search(r"(20\d{2}[年\-/.]\d{1,2}[月\-/.]\d{1,2}(?:日)?(?:\s*[0-2]?\d[:：]\d{2})?)", text or "")
    if not match:
        return None
    return _parse_datetime_text(match.group(1))


def _parse_datetime_text(text: str) -> Optional[dt.datetime]:
    raw = (text or "").strip()
    match = re.search(r"(20\d{2})[年\-/.](\d{1,2})[月\-/.](\d{1,2})(?:日)?(?:\s*(\d{1,2})[:：](\d{2}))?", raw)
    if not match:
        return None
    try:
        hour = min(max(int(match.group(4) or 23), 0), 23)
        minute = min(max(int(match.group(5) or 59), 0), 59)
        return dt.datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), hour, minute)
    except Exception:
        return None


def _select_items_with_llm(section_name: str, items: List[dict], limit: int) -> List[dict]:
    if not getattr(config, "LLM_ENABLED", False):
        return []

    candidates = []
    for index, item in enumerate(items, start=1):
        content = _clean_text(item.get("content", ""))[:500]
        candidates.append(
            f"{index}. 标题: {item.get('title', '')}\n"
            f"发布日期: {item.get('date', '')}\n"
            f"正文摘录: {content}"
        )

    system_prompt = (
        "????????????????????????"
        "???????????????????? {limit} ??"
        "???????????????????"
        "??????????????????"
        "????????????????????????????"
        "???????????????????????????????????????"
        '??? JSON???? {{"keep_indices": [1,2,3]}}?'
    ).format(limit=limit)
    user_prompt = f"栏目: {section_name}\n\n" + "\n\n".join(candidates)
    result = chat_complete(
        system_prompt,
        user_prompt,
        max_tokens=180,
        temperature=0,
        task_label=f"正在筛选{section_name}保留条目",
    )
    if not result:
        return []

    match = re.search(r"\{[\s\S]*\}", result)
    if not match:
        return []
    try:
        payload = __import__("json").loads(match.group(0))
    except Exception:
        return []

    selected = []
    for value in payload.get("keep_indices") or []:
        try:
            idx = int(value) - 1
        except Exception:
            continue
        if 0 <= idx < len(items) and items[idx] not in selected:
            selected.append(items[idx])
    return selected[:limit]


def _enrich_items(section_name: str, items: List[dict]) -> List[dict]:
    enriched = []
    for item in items:
        copied = dict(item)
        copied["summary"] = _summarize_item(copied)
        copied["content"] = _compress_item_content(copied, copied["summary"])
        enriched.append(copied)
    return enriched


def _summarize_item(item: dict) -> str:
    title = item.get("title", "")
    content = item.get("content", "")
    fallback = _clip_units(_clean_text(content), SUMMARY_HARD_LIMIT)
    if not getattr(config, "LLM_ENABLED", False):
        return fallback

    result = chat_complete(
        (
            "你在为清华大学物理系的每周信息简报写要点透视。"
            "请概括最重要的信息，优先保留活动/截止/报名/地点/对象。"
            f"输出不超过 {SUMMARY_HARD_LIMIT} 字，只输出摘要正文。"
        ),
        f"标题: {title}\n来源: {item.get('source', '')}\n正文:\n{content[:2500]}",
        max_tokens=180,
        temperature=0.2,
        task_label=f"正在压缩单条信息篇幅：{title[:24]}",
    )
    return _clip_units(_clean_text(result or fallback), SUMMARY_HARD_LIMIT)


def _compress_item_content(item: dict, summary: str) -> str:
    content = item.get("content", "") or ""
    budget = max(80, ITEM_TOTAL_UNIT_LIMIT - _estimate_units(summary) - 20)
    cleaned = _clean_text(content)
    if _estimate_units(summary) + _estimate_units(cleaned) <= ITEM_TOTAL_UNIT_LIMIT:
        return cleaned

    if getattr(config, "LLM_ENABLED", False):
        result = chat_complete(
            (
                "请把下面的通知正文压缩成精炼版，保留事实，不要捏造。"
                "优先保留时间、地点、截止、对象、报名方式和必要背景。"
                f"输出控制在约 {budget} 字以内，可保留简短分行。"
            ),
            f"标题: {item.get('title', '')}\n正文:\n{content[:3500]}",
            max_tokens=300,
            temperature=0.2,
            task_label=f"正在压缩正文内容：{item.get('title', '')[:24]}",
        )
        if result:
            candidate = _clean_text(result)
            if _estimate_units(summary) + _estimate_units(candidate) <= ITEM_TOTAL_UNIT_LIMIT:
                return candidate
            return _clip_units(candidate, budget)

    return _clip_units(cleaned, budget)


def _clean_text(text: str) -> str:
    cleaned = text or ""
    cleaned = re.sub(r"\r\n?", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def _estimate_units(text: str) -> int:
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text or ""))
    english = len(re.findall(r"[A-Za-z0-9_]+", text or ""))
    return chinese + english


def _clip_units(text: str, limit: int) -> str:
    result = []
    units = 0
    for token in re.finditer(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+|\s+|.", text or ""):
        part = token.group(0)
        part_units = 0
        if re.fullmatch(r"[\u4e00-\u9fff]", part):
            part_units = 1
        elif re.fullmatch(r"[A-Za-z0-9_]+", part):
            part_units = 1
        if units + part_units > limit:
            break
        units += part_units
        result.append(part)
    return "".join(result).strip()


def _extract_inline_date(text: str) -> str:
    match = re.search(r"(20\d{2}[\-/.年]\d{1,2}[\-/.月]\d{1,2})", text or "")
    if not match:
        return ""
    value = match.group(1).replace("年", "-").replace("月", "-").replace("日", "")
    value = value.replace("/", "-").replace(".", "-")
    parts = [part for part in value.split("-") if part]
    if len(parts) >= 3:
        return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
    return value


def _generate_transition(section_name: str, summaries: Iterable[str], has_items: bool) -> str:
    if getattr(config, "LLM_TRANSITION_ENABLED", False):
        joined = "\n".join(f"- {item}" for item in summaries if item) or "本周没有内容。"
        result = chat_complete(
            getattr(config, "LLM_TRANSITION_SYSTEM_PROMPT", "请写一句栏目导语。"),
            f"栏目: {section_name}\n{joined}",
            max_tokens=80,
            temperature=0.4,
            task_label=f"正在生成栏目导语：{section_name}",
        )
        if result:
            return result.strip()

    defaults = getattr(config, "SECTION_DEFAULT_TRANSITIONS", {})
    if not has_items:
        return defaults.get("EMPTY", "本周暂无相关信息。")
    return defaults.get(section_name, "下面来看看本周值得关注的内容。")
