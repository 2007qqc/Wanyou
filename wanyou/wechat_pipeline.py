import datetime
import json
import os
import re

import config
from wanyou.decider import apply_keyword_rules, should_copy_with_llm
from wanyou.filter_debug import log_filter_decision
from wanyou.temporal_filter import assess_temporal_relevance
from wanyou.utils_issue_filter import current_issue_cutoff
from wanyou.wechat_client import create_api_session, dedupe_items, fetch_articles, resolve_fakeids
from wanyou.wechat_content import enrich_items_with_content
from wanyou.utils_html import clean_crawled_markdown
from wanyou.utils_llm import chat_complete


NO_WECHAT_MATCH_MESSAGE = "本期没有符合条件的最新公众号信息。"


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
    should_filter = getattr(config, "WECHAT_FILTER_MD_WITH_LLM", False)
    fallback_keep = getattr(config, "WECHAT_FILTER_FALLBACK_KEEP", True)

    for item in items:
        if not should_filter:
            item["include_in_md"] = True
            item["decision_source"] = "after_temporal_filter"
            log_filter_decision(
                section="wechat",
                title=item.get("title") or "",
                status="kept",
                reason="after_temporal_filter",
                stage="wechat_mark_items",
                date=format_datetime_text(item),
                url=item.get("url") or "",
                source=item.get("account_keyword") or "",
            )
            continue

        title = item.get("title") or ""
        date = format_datetime_text(item)
        snippet = _build_filter_snippet(item)

        rule_decision = apply_keyword_rules(title, snippet)
        if rule_decision is not None:
            item["include_in_md"] = bool(rule_decision)
            item["decision_source"] = "keyword_rule"
            log_filter_decision(
                section="wechat",
                title=title,
                status="kept" if rule_decision else "dropped",
                reason="keyword_rule",
                stage="wechat_mark_items",
                date=date,
                url=item.get("url") or "",
                source=item.get("account_keyword") or "",
            )
            continue

        decision = should_copy_with_llm("wechat", title, date, snippet)
        if decision is None:
            item["include_in_md"] = bool(fallback_keep)
            item["decision_source"] = "fallback_keep" if fallback_keep else "fallback_drop"
        else:
            item["include_in_md"] = bool(decision)
            item["decision_source"] = "llm"
        log_filter_decision(
            section="wechat",
            title=title,
            status="kept" if item.get("include_in_md") else "dropped",
            reason=item.get("decision_source") or "unknown",
            stage="wechat_mark_items",
            date=date,
            url=item.get("url") or "",
            source=item.get("account_keyword") or "",
        )


def _fallback_wechat_summary(item):
    for candidate in (item.get("digest") or "", item.get("content") or ""):
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
        temperature=0,
        task_label=f"正在总结公众号内容：{title[:24]}",
    )
    if result:
        cleaned = re.sub(r"\s+", " ", result).strip()
        if cleaned:
            return cleaned[: getattr(config, "LLM_SUMMARY_MAX_CHARS", 100)]
    return _fallback_wechat_summary(item)


def _prefilter_recent_wechat_items(items, days_limit=None):
    if not items:
        return []

    if days_limit:
        cutoff_dt = datetime.datetime.now() - datetime.timedelta(days=max(int(days_limit), 0))
    else:
        cutoff_dt = current_issue_cutoff()
    cutoff_ts = int(cutoff_dt.timestamp())

    kept = []
    for item in items:
        title = item.get("title") or ""
        publish_text = format_datetime_text(item)
        ts = item.get("timestamp")
        if ts is None:
            kept.append(item)
            log_filter_decision(
                section="wechat",
                title=title,
                status="kept",
                reason="publish_time_missing_keep_for_review",
                stage="wechat_publish_prefilter",
                date=publish_text,
                url=item.get("url") or "",
                source=item.get("account_keyword") or "",
            )
            continue
        if ts >= cutoff_ts:
            kept.append(item)
            log_filter_decision(
                section="wechat",
                title=title,
                status="kept",
                reason="publish_recent",
                stage="wechat_publish_prefilter",
                date=publish_text,
                url=item.get("url") or "",
                source=item.get("account_keyword") or "",
            )
        else:
            log_filter_decision(
                section="wechat",
                title=title,
                status="dropped",
                reason="publish_older_than_cutoff",
                stage="wechat_publish_prefilter",
                date=publish_text,
                url=item.get("url") or "",
                source=item.get("account_keyword") or "",
                details={"cutoff": cutoff_dt.isoformat(timespec="minutes")},
            )
    return kept


def collect_wechat_items(days_limit=None):
    timeout = getattr(config, "WECHAT_REQUEST_TIMEOUT", 15)
    sleep_seconds = getattr(config, "WECHAT_SLEEP_SECONDS", 1)

    print("公众号：正在创建 API 会话")
    session = create_api_session()
    accounts = resolve_fakeids(session, timeout)
    print(f"公众号：共匹配 {len(accounts)} 个账号，开始抓取推送")

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
    for item in items:
        log_filter_decision(
            section="wechat",
            title=item.get("title") or "",
            status="found",
            reason="api_article",
            stage="wechat_collect",
            date=format_datetime_text(item),
            url=item.get("url") or "",
            source=item.get("account_keyword") or "",
        )

    items = _prefilter_recent_wechat_items(items, days_limit=days_limit)
    print(f"公众号：按发布时间初筛后保留 {len(items)} 条候选推送")

    print(f"公众号：将下载 {len(items)} 条候选推送正文")
    enrich_items_with_content(session, items, timeout, sleep_seconds)
    if getattr(config, "RAW_COLLECTION_MODE", False):
        raw_items = []
        for item in items:
            item["include_in_md"] = True
            item["decision_source"] = "raw_publish_recent"
            raw_items.append(item)
        print(f"公众号 raw：按发布时间保留 {len(raw_items)} 条候选推送")
        return raw_items
    temporally_kept = []
    total_items = len(items)
    for index, item in enumerate(items, start=1):
        print(f"公众号：正在进行时效判断 {index}/{total_items}：{(item.get('account_keyword') or '未知公众号')} - {(item.get('title') or '无标题')[:40]}")
        title = item.get("title") or ""
        publish_date = format_datetime_text(item)
        temporal_text = "\n".join(
            part
            for part in [
                title,
                item.get("digest") or "",
                item.get("publish_time") or "",
                item.get("content") or "",
                "\n".join(item.get("image_ocr_texts", []) or []),
            ]
            if part
        )
        assessment = assess_temporal_relevance(
            text=temporal_text,
            fallback_publish_date=publish_date,
        )
        log_filter_decision(
            section="wechat",
            title=title,
            status="kept" if assessment.get("keep") else "dropped",
            reason=str(assessment.get("reason") or "temporal_unknown"),
            stage="wechat_temporal_filter",
            date=publish_date,
            url=item.get("url") or "",
            source=item.get("account_keyword") or "",
            details={
                "basis": assessment.get("basis", ""),
                "now": assessment.get("now", ""),
                "cutoff": assessment.get("cutoff", ""),
                "signals": assessment.get("signals", []),
            },
        )
        if assessment.get("keep"):
            temporally_kept.append(item)
    items = temporally_kept

    for index, item in enumerate(items, start=1):
        print(f"公众号：正在总结保留推送 {index}/{len(items)}：{(item.get('account_keyword') or '未知公众号')} - {(item.get('title') or '无标题')[:40]}")
        item["content"] = clean_crawled_markdown(item.get("content") or "", source=item.get("title", "wechat"))
        item["digest"] = clean_crawled_markdown(item.get("digest") or "", source=item.get("title", "wechat"))
        item["summary"] = summarize_wechat_item(item)
    mark_items_for_md(items)
    visible_count = sum(1 for item in items if item.get("include_in_md", True))
    print(f"公众号：筛选完成，保留 {visible_count} 条进入万有预报")
    return items


def write_md(items, output_path, include_content=True, header="# 其他公众号公开历史文章"):
    with open(output_path, "w", encoding="utf-8") as f:
        write_md_stream(items, f, include_content=include_content, header=header)


def write_md_stream(items, stream, include_content=True, header="# 其他公众号公开历史文章"):
    stream.write(f"{header}\n\n")
    visible_items = [item for item in items if item.get("include_in_md", True)]
    if not visible_items:
        stream.write(f"## 占位卡片\n\n{NO_WECHAT_MATCH_MESSAGE}\n\n")
        return

    for item in visible_items:
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

    welfare_keywords = ["公益", "志愿", "志愿者", "支教", "捐赠", "义卖", "献血", "助残", "环保", "募捐", "慈善"]
    club_keywords = ["社团", "协会", "俱乐部", "招新", "百团", "工作坊", "学生组织", "兴趣小组"]

    if "学生会" in account_keyword or "学生会" in title:
        return "学生会信息"
    if any(keyword in account_keyword for keyword in ["青年科创", "青年科协"]) or any(
        keyword in text for keyword in ["科协", "科创", "青科", "创新", "创业"]
    ):
        return "青年科协信息"
    if any(keyword in text for keyword in welfare_keywords):
        return "学生公益信息"
    if any(keyword in text for keyword in club_keywords):
        return "学生社团信息"
    return "其他公众号信息"


def split_wechat_items_by_section(items):
    buckets = {section: [] for section in WECHAT_SECTION_ORDER}
    for item in items:
        if not item.get("include_in_md", True):
            log_filter_decision(
                section="wechat",
                title=item.get("title") or "",
                status="dropped",
                reason=item.get("decision_source") or "include_in_md_false",
                stage="wechat_sectioning",
                date=format_datetime_text(item),
                url=item.get("url") or "",
                source=item.get("account_keyword") or "",
            )
            continue
        section = _wechat_section_for_item(item)
        log_filter_decision(
            section=section,
            title=item.get("title") or "",
            status="kept",
            reason="assigned_wechat_section",
            stage="wechat_sectioning",
            date=format_datetime_text(item),
            url=item.get("url") or "",
            source=item.get("account_keyword") or "",
        )
        buckets.setdefault(section, []).append(item)
    return buckets


def write_sectioned_md_stream(items, stream, include_content=True):
    buckets = split_wechat_items_by_section(items)
    wrote_any = False
    for section in WECHAT_SECTION_ORDER:
        section_items = buckets.get(section) or []
        if not section_items:
            log_filter_decision(section=section, title="", status="empty", reason="no_visible_wechat_items", stage="wechat_sectioning")
            continue
        wrote_any = True
        write_md_stream(section_items, stream, include_content=include_content, header=f"# {section}")
    if not wrote_any:
        stream.write("# 其他公众号信息\n\n")
        stream.write(f"## 占位卡片\n\n{NO_WECHAT_MATCH_MESSAGE}\n\n")


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
