from typing import Iterable, List

import config
from wanyou.utils_llm import chat_complete


def summarize_item(title: str, content: str, source: str = "", date: str = "") -> str:
    if not getattr(config, "LLM_SUMMARY_ENABLED", False):
        return _fallback_summary(content)

    prompt = f"标题: {title}\n来源: {source}\n日期: {date}\n正文:\n{content[:2000]}"
    result = chat_complete(
        config.LLM_SUMMARY_SYSTEM_PROMPT,
        prompt,
        max_tokens=160,
        temperature=0.3,
    )
    if not result:
        return _fallback_summary(content)
    return result.strip()[: config.LLM_SUMMARY_MAX_CHARS]


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
    text = " ".join((content or "").split())
    return text[: config.LLM_SUMMARY_MAX_CHARS]


def _fallback_transition(section_name: str, has_content: bool) -> str:
    defaults = getattr(config, "SECTION_DEFAULT_TRANSITIONS", {})
    if not has_content:
        return defaults.get("EMPTY", "本周暂无相关信息。")
    return defaults.get(section_name, "下面来看本周值得关注的内容。")
