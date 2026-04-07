import datetime
import json
import os
import re

import config
from wanyou.decider import apply_keyword_rules, should_copy_with_llm
from wanyou.wechat_client import create_api_session, dedupe_items, fetch_articles, resolve_fakeids
from wanyou.wechat_content import enrich_items_with_content
from wanyou.utils_html import clean_crawled_markdown
from wanyou.utils_llm import chat_complete


def format_datetime_text(item):
    ts = item.get("timestamp")
    if ts:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    publish_time = (item.get("publish_time") or "").strip()
    return publish_time or "N/A"


def _build_filter_snippet(item):
    parts = []
    digest = (item.get("digest") or "").strip()
    if digest:
        parts.append(f"摘要: {digest}")

    content = (item.get("content") or "").strip()
    if content:
        parts.append(f"正文: {content}")

    ocr_texts = [text.strip() for text in item.get("image_ocr_texts", []) if text and text.strip()]
    if ocr_texts:
        parts.append("图片文字: " + "\n".join(ocr_texts))

    snippet = "\n".join(parts)
    max_chars = getattr(config, "WECHAT_FILTER_CONTENT_MAX_CHARS", 3000)
    if max_chars and len(snippet) > max_chars:
        snippet = snippet[:max_chars]
    return snippet


def mark_items_for_md(items):
    should_filter = getattr(config, "WECHAT_FILTER_MD_WITH_LLM", True)
    fallback_keep = getattr(config, "WECHAT_FILTER_FALLBACK_KEEP", True)

    for item in items:
        if not should_filter:
            item["include_in_md"] = True
            item["decision_source"] = "disabled"
            continue

        title = item.get("title") or ""
        date = format_datetime_text(item)
        snippet = _build_filter_snippet(item)

        rule_decision = apply_keyword_rules(title, snippet)
        if rule_decision is not None:
            item["include_in_md"] = bool(rule_decision)
            item["decision_source"] = "keyword_rule"
            continue

        decision = should_copy_with_llm("wechat", title, date, snippet)
        if decision is None:
            item["include_in_md"] = bool(fallback_keep)
            item["decision_source"] = "fallback_keep" if fallback_keep else "fallback_drop"
        else:
            item["include_in_md"] = bool(decision)
            item["decision_source"] = "llm"


def _filter_recent_days(items, days_limit):
    if not days_limit:
        return items
    cutoff = int((datetime.datetime.now() - datetime.timedelta(days=days_limit)).timestamp())
    filtered = []
    for item in items:
        ts = item.get("timestamp")
        if ts is None or ts >= cutoff:
            filtered.append(item)
    return filtered


def _fallback_wechat_summary(item):
    for candidate in (
        item.get("digest") or "",
        item.get("content") or "",
    ):
        cleaned = clean_crawled_markdown(candidate, source=item.get("title", "wechat"))
        if cleaned:
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            return cleaned[: getattr(config, "LLM_SUMMARY_MAX_CHARS", 100)]
    return ""


def summarize_wechat_item(item):
    title = (item.get("title") or "").strip()
    digest = clean_crawled_markdown(item.get("digest") or "", source=title)
    content = clean_crawled_markdown(item.get("content") or "", source=title)
    snippet = "\n".join(part for part in [digest, content] if part).strip()
    if not snippet:
        return ""

    system_prompt = (
        "You are editing a concise campus briefing.\n"
        "Summarize the article in simplified Chinese within 90 characters.\n"
        "Keep only the most useful student-facing information such as theme, time, place, registration, deadline, or audience.\n"
        "Do not copy long original paragraphs.\n"
        "Return summary text only."
    )
    user_prompt = (
        f"标题: {title}\n"
        f"日期: {format_datetime_text(item)}\n"
        f"来源公众号: {(item.get('account_keyword') or '').strip()}\n"
        f"内容:\n{snippet[:2500]}"
    )
    result = chat_complete(
        system_prompt,
        user_prompt,
        max_tokens=160,
        temperature=0.2,
    )
    if result:
        cleaned = re.sub(r"\s+", " ", result).strip()
        if cleaned:
            return cleaned[: getattr(config, "LLM_SUMMARY_MAX_CHARS", 100)]
    return _fallback_wechat_summary(item)


def collect_wechat_items(days_limit=None):
    timeout = getattr(config, "WECHAT_REQUEST_TIMEOUT", 15)
    sleep_seconds = getattr(config, "WECHAT_SLEEP_SECONDS", 1)

    session = create_api_session()
    accounts = resolve_fakeids(session, timeout)

    items = []
    for account in accounts:
        items.extend(
            fetch_articles(
                session,
                account["fakeid"],
                timeout,
                account_keyword=account.get("keyword", ""),
            )
        )

    items = dedupe_items(items)
    items.sort(key=lambda item: item.get("timestamp") or 0, reverse=True)
    items = _filter_recent_days(items, days_limit)

    max_articles = getattr(config, "WECHAT_MAX_ARTICLES", 0)
    if max_articles and len(items) > max_articles:
        items = items[:max_articles]

    enrich_items_with_content(session, items, timeout, sleep_seconds)
    for item in items:
        item["content"] = clean_crawled_markdown(item.get("content") or "", source=item.get("title", "wechat"))
        item["summary"] = summarize_wechat_item(item)
    mark_items_for_md(items)
    return items


def write_md(items, output_path, include_content=True, header="# 其他公众号公开历史文章"):
    with open(output_path, "w", encoding="utf-8") as f:
        write_md_stream(items, f, include_content=include_content, header=header)


def write_md_stream(items, stream, include_content=True, header="# 其他公众号公开历史文章"):
    stream.write(f"{header}\n\n")
    for item in items:
        if not item.get("include_in_md", True):
            continue

        title = item.get("title") or "N/A"
        url = item.get("url") or "N/A"
        digest = item.get("digest") or ""
        account_keyword = item.get("account_keyword") or ""

        stream.write(f"## {title}\n\n")
        if account_keyword:
            stream.write(f"来源公众号: {account_keyword}\n\n")
        stream.write(f"日期: {format_datetime_text(item)}\n\n")
        stream.write(f"链接: {url}\n\n")

        publish_time = item.get("publish_time") or ""
        author = item.get("author") or ""
        if publish_time:
            stream.write(f"发布时间: {publish_time}\n\n")
        if author:
            stream.write(f"作者: {author}\n\n")
        summary = (item.get("summary") or "").strip()
        if summary:
            stream.write(f"摘要: {summary}\n\n")
        elif digest:
            stream.write(f"摘要: {digest}\n\n")

        if include_content:
            content = item.get("content") or ""
            if content:
                stream.write("内容:\n\n")
                stream.write(content)
                if not content.endswith("\n"):
                    stream.write("\n")
                stream.write("\n")


WECHAT_SECTION_ORDER = [
    "学生会信息",
    "青年科协信息",
    "学生社团信息",
    "学生公益信息",
    "其他公众号信息",
]


def _wechat_section_for_item(item):
    account_keyword = (item.get("account_keyword") or "").strip()
    title = (item.get("title") or "").strip()
    digest = (item.get("digest") or "").strip()
    content = (item.get("content") or "").strip()
    text = "\n".join([account_keyword, title, digest, content]).lower()

    welfare_keywords = [
        "公益", "志愿", "志愿者", "支教", "捐赠", "义卖", "献血", "助残", "环保", "募捐", "慈善",
    ]
    club_keywords = [
        "社团", "协会", "俱乐部", "招新", "百团", "工作坊", "学生组织", "兴趣小组",
    ]

    if any(keyword in text for keyword in welfare_keywords):
        return "学生公益信息"
    if "学生会" in account_keyword or "学生会" in title:
        return "学生会信息"
    if any(keyword in account_keyword for keyword in ["青年科创", "青年科协"]) or any(
        keyword in text for keyword in ["科协", "科创", "青科", "创新", "创业"]
    ):
        return "青年科协信息"
    if any(keyword in text for keyword in club_keywords):
        return "学生社团信息"
    return "其他公众号信息"


def split_wechat_items_by_section(items):
    buckets = {section: [] for section in WECHAT_SECTION_ORDER}
    for item in items:
        if not item.get("include_in_md", True):
            continue
        section = _wechat_section_for_item(item)
        buckets.setdefault(section, []).append(item)
    return buckets


def write_sectioned_md_stream(items, stream, include_content=True):
    buckets = split_wechat_items_by_section(items)
    for section in WECHAT_SECTION_ORDER:
        section_items = buckets.get(section) or []
        if not section_items:
            continue
        write_md_stream(
            section_items,
            stream,
            include_content=False,
            header=f"# {section}",
        )


def write_json(items, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def run_wechat_public_output(days_limit=None):
    items = collect_wechat_items(days_limit=days_limit)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    output_base = os.path.join(config.OUTPUT_DIR, f"wechat_{timestamp}")
    if config.WECHAT_OUTPUT_FORMAT == "json":
        output_path = f"{output_base}.json"
        write_json(items, output_path)
    else:
        output_path = f"{output_base}.md"
        write_md(items, output_path, include_content=False)
    return output_path, items
