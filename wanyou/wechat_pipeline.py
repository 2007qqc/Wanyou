import datetime
import json
import os

import config
from wanyou.decider import apply_keyword_rules, should_copy_with_llm
from wanyou.wechat_client import create_api_session, dedupe_items, fetch_articles, resolve_fakeid
from wanyou.wechat_content import enrich_items_with_content


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
        if ts is None:
            filtered.append(item)
            continue
        if ts >= cutoff:
            filtered.append(item)
        else:
            # 列表一般按时间倒序，提前终止可减少无效请求
            break
    return filtered


def collect_wechat_items(days_limit=None):
    timeout = getattr(config, "WECHAT_REQUEST_TIMEOUT", 15)
    sleep_seconds = getattr(config, "WECHAT_SLEEP_SECONDS", 1)

    session = create_api_session()
    fakeid = resolve_fakeid(session, timeout)
    items = fetch_articles(session, fakeid, timeout)
    items = dedupe_items(items)
    items = _filter_recent_days(items, days_limit)

    max_articles = getattr(config, "WECHAT_MAX_ARTICLES", 0)
    if max_articles and len(items) > max_articles:
        items = items[:max_articles]

    enrich_items_with_content(session, items, timeout, sleep_seconds)
    mark_items_for_md(items)
    return items


def write_md(items, output_path, include_content=True, header="# 公众号公开历史文章"):
    with open(output_path, "w", encoding="utf-8") as f:
        write_md_stream(items, f, include_content=include_content, header=header)


def write_md_stream(items, stream, include_content=True, header="# 公众号公开历史文章"):
    stream.write(f"{header}\n\n")
    for item in items:
        if not item.get("include_in_md", True):
            continue

        title = item.get("title") or "N/A"
        url = item.get("url") or "N/A"
        digest = item.get("digest") or ""

        stream.write(f"## {title}\n\n")
        stream.write(f"日期: {format_datetime_text(item)}\n\n")
        stream.write(f"链接: {url}\n\n")

        publish_time = item.get("publish_time") or ""
        author = item.get("author") or ""
        if publish_time:
            stream.write(f"发布时间: {publish_time}\n\n")
        if author:
            stream.write(f"作者: {author}\n\n")
        if digest:
            stream.write(f"摘要: {digest}\n\n")

        if include_content:
            content = item.get("content") or ""
            if content:
                stream.write("内容:\n\n")
                stream.write(content)
                if not content.endswith("\n"):
                    stream.write("\n")
                stream.write("\n")


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
        write_md(items, output_path, include_content=getattr(config, "WECHAT_FETCH_CONTENT", True))
    return output_path, items
