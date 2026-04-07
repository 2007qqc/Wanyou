import re
from typing import Iterable, List

import config
from wanyou.utils_llm import chat_complete


def summarize_item(title: str, content: str, source: str = "", date: str = "") -> str:
    structured_summary = _structured_summary(content, source=source)
    if not getattr(config, "LLM_SUMMARY_ENABLED", False):
        return _finalize_summary(structured_summary or _fallback_summary(content))

    prompt = f"标题: {title}\n来源: {source}\n日期: {date}\n正文:\n{content[:2000]}"
    result = chat_complete(
        config.LLM_SUMMARY_SYSTEM_PROMPT,
        prompt,
        max_tokens=160,
        temperature=0.3,
    )
    if not result:
        return _finalize_summary(structured_summary or _fallback_summary(content))
    return _finalize_summary(result.strip()[: config.LLM_SUMMARY_MAX_CHARS])


def generate_transition(section_name: str, summaries: Iterable[str]) -> str:
    summary_list = [item.strip() for item in summaries if item and item.strip()]
    if not getattr(config, "LLM_TRANSITION_ENABLED", False):
        return _fallback_transition(section_name, bool(summary_list))

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
    )
    if not result:
        return _fallback_transition(section_name, bool(summary_list))
    return result.strip()


def enrich_markdown_section(section_name: str, items: List[dict]) -> List[dict]:
    enriched = []
    for item in items:
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


def build_augmented_markdown(markdown_text: str) -> str:
    rendered_sections = []
    for section in parse_markdown_document(markdown_text):
        items = []
        for item in section["items"]:
            body = "\n".join(item["body_lines"]).strip()
            items.append(
                {
                    "title": item["title"],
                    "content": body,
                    "source": section["title"],
                }
            )
        enriched = enrich_markdown_section(section["title"], items)
        transition = generate_transition(
            section["title"],
            [item.get("summary", "") for item in enriched],
        )

        parts = [f"# {section['title']}", "", transition, ""]
        for item in enriched:
            parts.append(f"## {item['title']}")
            parts.append("")
            if item.get("summary"):
                parts.append(f"要点透视：{item['summary']}")
                parts.append("")
            content = item.get("content", "").strip()
            if content:
                parts.append(content)
                parts.append("")
        rendered_sections.append("\n".join(parts).strip())

    return "\n\n".join(section for section in rendered_sections if section).strip() + "\n"


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
    return compact[: config.LLM_SUMMARY_MAX_CHARS]


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
    return compact[: config.LLM_SUMMARY_MAX_CHARS]


def _finalize_summary(summary: str) -> str:
    cleaned_summary = _clip_summary(summary)
    if cleaned_summary and _looks_like_complete_summary(cleaned_summary):
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
    return cleaned.strip(" ：:|")


def _is_metadata_paragraph(text: str) -> bool:
    compact = _clean_summary_text(text)
    if not compact:
        return True

    metadata_label_pattern = (
        r"^(?:日期|时间|地点|链接|票价|报告人|报告时间|报告地点|发布日期|地点提示|主讲|嘉宾|来源|浏览|点击|作者)[：:]"
    )
    if all(
        re.match(metadata_label_pattern, part.strip()) or not re.search(r"[\u4e00-\u9fffA-Za-z]", part)
        for part in re.split(r"[；;|]", compact)
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
            new_text = re.sub(pattern, "", cleaned).lstrip(" ，,；;|")
            if new_text != cleaned:
                cleaned = new_text
                changed = True

    return cleaned.strip()


def _fallback_transition(section_name: str, has_content: bool) -> str:
    defaults = getattr(config, "SECTION_DEFAULT_TRANSITIONS", {})
    if not has_content:
        return defaults.get("EMPTY", "本周暂无相关信息。")
    return defaults.get(section_name, "下面来看本周值得关注的内容。")
