import datetime as dt
import os
import re
from typing import Iterable, List, Optional

import config
from wanyou.markdown_document import parse_markdown_document
from wanyou.prompt_preferences import KEEP_DROP_PREFERENCE_RULES
from wanyou.utils_llm import chat_complete
from wanyou.filter_debug import configure_filter_debug_from_markdown, log_filter_decision
from wanyou.run_clock import effective_run_datetime
from wanyou.temporal_filter import assess_temporal_relevance


MAX_ITEMS_PER_SECTION = 4
WECHAT_MAX_ITEMS = 5
NOW = effective_run_datetime()
PHYSICS_SECTION = "物理系学术报告"


def build_augmented_markdown(markdown_text: str, current_markdown_path: str = "") -> str:
    configure_filter_debug_from_markdown(current_markdown_path)
    rendered_sections = []
    trust_selected_raw = "_todo_selected_raw" in os.path.basename(current_markdown_path or "")

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

        items = _filter_temporal_items(section_name, items) if not trust_selected_raw else items
        items = _filter_section_items(section_name, items)
        for item in items:
            log_filter_decision(
                section=section_name,
                title=item.get("title", ""),
                status="kept",
                reason="selected_for_final_markdown",
                stage="synthesizer",
                date=item.get("date", ""),
            )
        enriched = _enrich_items(section_name, items)
        transition = _generate_transition(section_name, [item.get("summary", "") for item in enriched], bool(enriched))

        parts = [f"# {section_name}", ""]
        if transition:
            parts += [transition, ""]
        for item in enriched:
            parts.append(f"## {item['title']}")
            parts.append("")
            if item.get("summary") and not _summary_repeats_content(item.get("summary", ""), item.get("content", "")):
                parts.append(f"要点透视：{item['summary']}")
                parts.append("")
            if item.get("content"):
                parts.append(item["content"])
                parts.append("")
        rendered_sections.append("\n".join(parts).strip())

    return "\n\n".join(section for section in rendered_sections if section).strip() + "\n"


def _filter_temporal_items(section_name: str, items: List[dict]) -> List[dict]:
    filtered = []
    for item in items:
        title = item.get("title", "")
        content = item.get("content", "")
        publish_date = item.get("date", "")
        assessment = assess_temporal_relevance(
            text=f"{title}\n{content}",
            fallback_publish_date=publish_date,
            now=NOW,
        )
        log_filter_decision(
            section=section_name,
            title=title,
            status="kept" if assessment.get("keep") else "dropped",
            reason=str(assessment.get("reason") or "temporal_unknown"),
            stage="temporal_filter",
            date=publish_date,
            details={
                "basis": assessment.get("basis", ""),
                "now": assessment.get("now", ""),
                "cutoff": assessment.get("cutoff", ""),
                "signals": assessment.get("signals", []),
            },
        )
        if assessment.get("keep"):
            filtered.append(item)
    return filtered


def _filter_section_items(section_name: str, items: List[dict]) -> List[dict]:
    if not items:
        return []

    if section_name == PHYSICS_SECTION:
        active_items = []
        for item in items:
            if _physics_item_is_expired(item):
                log_filter_decision(
                    section=section_name,
                    title=item.get("title", ""),
                    status="dropped",
                    reason="expired_physics_event",
                    stage="synthesizer_filter",
                    date=item.get("date", ""),
                )
            else:
                active_items.append(item)
        active_items.sort(key=lambda item: _extract_inline_datetime(item.get("content", "")) or dt.datetime.min, reverse=True)
        for item in active_items[MAX_ITEMS_PER_SECTION:]:
            log_filter_decision(
                section=section_name,
                title=item.get("title", ""),
                status="dropped",
                reason="max_items_per_section",
                stage="synthesizer_filter",
                date=item.get("date", ""),
                details={"limit": MAX_ITEMS_PER_SECTION},
            )
        return active_items[:MAX_ITEMS_PER_SECTION]

    if section_name == "其他公众号信息":
        for item in items[WECHAT_MAX_ITEMS:]:
            log_filter_decision(
                section=section_name,
                title=item.get("title", ""),
                status="dropped",
                reason="max_wechat_items",
                stage="synthesizer_filter",
                date=item.get("date", ""),
                details={"limit": WECHAT_MAX_ITEMS},
            )
        return items[:WECHAT_MAX_ITEMS]

    if len(items) <= MAX_ITEMS_PER_SECTION:
        return items

    selected = _select_items_with_llm(section_name, items, MAX_ITEMS_PER_SECTION)
    if selected:
        selected_ids = {id(item) for item in selected}
        for item in items:
            if id(item) not in selected_ids:
                log_filter_decision(
                    section=section_name,
                    title=item.get("title", ""),
                    status="dropped",
                    reason="llm_section_selection",
                    stage="synthesizer_filter",
                    date=item.get("date", ""),
                    details={"limit": MAX_ITEMS_PER_SECTION},
                )
        return selected
    for item in items[MAX_ITEMS_PER_SECTION:]:
        log_filter_decision(
            section=section_name,
            title=item.get("title", ""),
            status="dropped",
            reason="fallback_max_items_per_section",
            stage="synthesizer_filter",
            date=item.get("date", ""),
            details={"limit": MAX_ITEMS_PER_SECTION},
        )
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
    match = re.search(r"(20\d{2})[年\-/.](\d{1,2})[月\-/.](\d{1,2})(?:[日号])?(?:\s*(\d{1,2})[:：](\d{2}))?", raw)
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
        "你在为清华大学物理系本科生编辑每周《万有预报》。"
        + "请从物理系本科生的角度，从候选条目中选出最应该保留的信息，最多 {limit} 条。"
        + KEEP_DROP_PREFERENCE_RULES
        + "候选条目通常已经经过前置时效筛选，因此不要机械地按发布时间远近排序。"
        + "如果正文表明活动已结束、报名已截止、影响时间已过，即使该条目在候选列表中，也不要保留。"
        + "优先保留课业相关信息，例如选课、排课、调课、调休、考试、培养方案、学籍和教务安排。"
        + "优先保留学术与培养相关信息，例如校内培养计划、星火计划、SRT、科研训练、讲座、报告、暑校和奖助机会。"
        + "优先保留物理系本科生可能参与或受影响的学生活动、学生权益、科创实践、志愿公益和校园生活信息。"
        + "重点查看时间戳、发布者、面向群体，再结合正文内容判断。"
        + "一般文化素质教育讲座、人文通识讲座、普通兴趣活动、组织宣传稿和围观型活动，通常应低于课业、物理学术和科研训练类信息。"
        + '只输出 JSON，格式为 {{"keep_indices": [1,2,3]}}。'
    ).format(limit=limit)
    user_prompt = f"栏目: {section_name}\n\n" + "\n\n".join(candidates)
    result = chat_complete(
        system_prompt,
        user_prompt,
        model=getattr(config, "SYNTHESIS_LLM_MODEL", "") or None,
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


_LEDE_META_RE = re.compile(
    r"[^。；！？]*?(?:未注明|未提及|未交代|未见说明|材料未|来源为|日期显示为|标注日期为)[^。；！？]*[。；！？]?"
)


def _tidy_lede(text: str, limit: int) -> str:
    """要点透视收尾：去掉编者视角的话，按整句收住，不要截成半句。

    公众号条目的正文里已经有 100 字左右的长摘要，要点透视再写 90 字两者就撞脸，
    所以带「来源公众号」的条目取摘要的第一句，长度控制在 45 字上下。
    """
    cleaned = _LEDE_META_RE.sub("", text or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) <= limit:
        return cleaned

    sentences = [part for part in re.split(r"(?<=[。；！？])", cleaned) if part.strip()]
    if sentences and len(sentences[0]) <= limit + 15:
        return sentences[0].strip()

    # 单句仍然太长：退到逗号处收住，补句号，绝不切在半句中间
    head = cleaned[: limit + 15]
    cut = max(head.rfind("，"), head.rfind("；"), head.rfind("、"))
    if cut >= limit * 0.5:
        return head[:cut].rstrip("，；、") + "。"
    return cleaned[:limit].rstrip("，；、") + "。"


def _norm_text(text: str) -> str:
    return re.sub(r"[\s\u3000，。；：、！？“”\"'（）()—\-·｜|]", "", text or "")


def _wechat_lede_from_digest(content: str, limit: int = 45) -> str:
    match = re.search(r"^摘要[:：]\s*(.+)$", content or "", re.MULTILINE)
    if not match:
        return ""
    return _tidy_lede(match.group(1).strip(), limit)


def _enrich_items(section_name: str, items: List[dict]) -> List[dict]:
    enriched = []
    for item in items:
        copied = dict(item)
        content = copied.get("content") or ""
        # 允许在选稿里手写「要点透视: …」把这一条的导语钉死（默认还是模型概括）。
        # 有些原文一开头就是已经过去的事（图书馆那条先讲中秋、国庆），模型照着写
        # 就会把过期信息放到最显眼的位置。
        pinned = re.search(r"^要点透视[:：]\s*(.+)$", content, re.MULTILINE)
        if pinned:
            content = re.sub(r"^要点透视[:：].*$\n?", "", content, count=1, flags=re.MULTILINE)
        washed = _clean_text(content)
        if pinned:
            copied["summary"] = pinned.group(1).strip()
        elif "来源公众号" in content:
            # 公众号条目：要点透视用摘要的第一句，摘要本身保持完整，两者不再重复
            copied["summary"] = _wechat_lede_from_digest(washed, 45)
        if not copied.get("summary"):
            copied["summary"] = _tidy_lede(_summarize_item(copied), 90)
        # 要点透视只是把标题又说一遍的（「推广｜项目信息 …」这种只有标题的推送），
        # 干脆不输出——卡片标题已经写了，再来一遍就是废话。
        if _norm_text(copied.get("summary", "")) and _norm_text(copied["summary"]) in _norm_text(item.get("title", "")):
            copied["summary"] = ""
        copied["content"] = washed
        enriched.append(copied)
    return enriched


def _summarize_item(item: dict) -> str:
    title = item.get("title", "")
    content = item.get("content", "")
    fallback = _clean_text(content)
    if not getattr(config, "LLM_ENABLED", False):
        return fallback

    result = chat_complete(
        (
            "你在为清华大学物理系的每周信息简报写要点透视。"
            "请概括最重要的信息，优先保留活动/截止/报名/地点/对象。"
            "输出控制在 100 字/词以内，只输出摘要正文。"
            "宁可略短，也不要为了凑长度截断成半句话。"
        ),
        f"标题: {title}\n来源: {item.get('source', '')}\n正文:\n{content[:2500]}",
        model=getattr(config, "SYNTHESIS_LLM_MODEL", "") or None,
        temperature=0,
        task_label=f"正在生成要点透视：{title[:24]}",
    )
    return _clean_text(result or fallback)


def _clean_text(text: str) -> str:
    cleaned = text or ""
    cleaned = re.sub(r"\r\n?", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def _summary_repeats_content(summary: str, content: str) -> bool:
    summary_key = re.sub(r"\s+", "", summary or "")
    content_key = re.sub(r"\s+", "", content or "")
    if not summary_key or not content_key:
        return False
    return content_key.startswith(summary_key) or summary_key == content_key


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
            model=getattr(config, "SYNTHESIS_LLM_MODEL", "") or None,
            temperature=0,
            task_label=f"正在生成栏目导语：{section_name}",
        )
        if result:
            return result.strip()

    defaults = getattr(config, "SECTION_DEFAULT_TRANSITIONS", {})
    if not has_items:
        return defaults.get("EMPTY", "本周暂无相关信息。")
    # 有内容的栏目不再写导语。之前按栏目硬编码的过渡句（「这周教务安排里有几条和课程
    # 节奏直接相关」「天气渐暖，楼里的讲座也慢慢热闹起来了」）每期都一样，和卡片标题
    # 重复，还常和当期事实矛盾（十月写「渐暖」）。栏目头（本期栏目 + 标题）已经把
    # 「这是什么栏目」说清楚了，导语只在显式开启 LLM_TRANSITION_ENABLED 时保留。
    return ""
