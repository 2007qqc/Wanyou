import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

import html2text
from selenium.webdriver.common.by import By

import config
from wanyou.decider import resolve_copy_decision
from wanyou.filter_debug import log_filter_decision
from wanyou.utils_issue_filter import current_issue_cutoff, load_previous_titles, seen_in_previous_issue, should_skip_by_time
from wanyou.utils_html import save_content
from wanyou.utils_llm import chat_complete
from wanyou.utils_web import build_requests_session, make_browser


DEFAULT_REPORT_KEYWORDS = [
    "学术报告",
    "学术讲座",
    "报告",
    "讲座",
    "seminar",
    "colloquium",
    "lecture",
]
DEFAULT_LOCATION_KEYWORDS = ["W101", "W105", "物理楼", "理科楼"]
DEFAULT_REPORT_EXCLUDE_KEYWORDS = [
    "学位授权点建设报告",
    "招聘信息",
    "导师及研究方向",
    "本科生工作组",
    "研究生工作组",
    "新闻动态",
    "公告",
]


def _config_keywords(name: str, fallback: list[str]) -> list[str]:
    raw = getattr(config, name, None)
    if not isinstance(raw, (list, tuple)):
        return fallback
    values = [str(item).strip() for item in raw if str(item).strip()]
    if not values:
        return fallback
    return values + [item for item in fallback if item not in values]


def _looks_like_report(title: str) -> bool:
    text = (title or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if any(keyword.lower() in lowered for keyword in DEFAULT_REPORT_EXCLUDE_KEYWORDS):
        return False
    keywords = _config_keywords("PHYSICS_REPORT_FORCE_KEYWORDS", DEFAULT_REPORT_KEYWORDS)
    return any(keyword.lower() in lowered for keyword in keywords)


def _looks_like_non_report_page(title: str, content_text: str = "") -> bool:
    text = "\n".join(part for part in [title or "", content_text or ""] if part).lower()
    if any(keyword.lower() in text for keyword in DEFAULT_REPORT_EXCLUDE_KEYWORDS):
        return True
    # These pages are usually navigation/administrative pages rather than actual reports.
    if "学位授权点建设" in text or "研究生工作组" in text:
        return True
    return False


def _normalize_text(html_text: str) -> str:
    handler = html2text.HTML2Text()
    handler.body_width = 0
    handler.single_line_break = True
    handler.ignore_links = False
    text = handler.handle(html_text or "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _text_quality_score(text: str) -> tuple[int, int, int]:
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    keywords = len(re.findall(r"报告|讲座|时间|地点|摘要|物理楼", text))
    mojibake = len(re.findall(r"[\u00c0-\u00ff]{2,}|锟|�", text))
    return chinese + keywords * 2, -mojibake, -len(text)


def _repair_mojibake_line(text: str) -> str:
    candidates = [text]
    for source_encoding in ("latin-1", "cp1252"):
        try:
            candidates.append(text.encode(source_encoding).decode("utf-8"))
        except Exception:
            continue
    return max(candidates, key=_text_quality_score)


def _clean_physics_text(text: str, title: str) -> str:
    cleaned_lines = []
    for raw_line in (text or "").replace("\ufeff", "").splitlines():
        line = _repair_mojibake_line(raw_line.rstrip())
        line = line.replace("报告 人", "报告人").replace("报告  人", "报告人")
        line = line.replace("内容摘要", "内容摘要")
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    start_markers = [
        "**报告题目",
        "报告题目：",
        f"### {title}",
        title,
    ]
    start_positions = [cleaned.find(marker) for marker in start_markers if marker and cleaned.find(marker) >= 0]
    if start_positions:
        cleaned = cleaned[min(start_positions):]

    end_markers = [
        "\n## ",
        "## ",
        "\n上一篇",
        "\n下一篇",
        "\n关闭窗口",
        "\n分享到",
        "\n版权所有",
        "\n地址：",
    ]
    end_positions = [cleaned.find(marker) for marker in end_markers if cleaned.find(marker) > 0]
    if end_positions:
        cleaned = cleaned[:min(end_positions)]

    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_date(text: str) -> str:
    match = re.search(r"(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?)", text or "")
    if not match:
        return ""
    date_text = match.group(1)
    date_text = date_text.replace("年", "-").replace("月", "-").replace("日", "")
    date_text = date_text.replace("/", "-").replace(".", "-")
    parts = [part.zfill(2) if index else part for index, part in enumerate(date_text.split("-"))]
    if len(parts) >= 3:
        return "-".join(parts[:3])
    return ""


def _extract_publish_date(title: str, content_text: str) -> str:
    for candidate in (_extract_date(content_text), _extract_date(title)):
        if candidate:
            return candidate
    return ""


def _extract_json_block(text: str) -> dict:
    if not text:
        return {}
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _extract_report_fields_with_llm(title: str, publish_date: str, detail_url: str, cleaned_text: str) -> dict:
    system_prompt = (
        "你负责从清华物理系学术报告原文中提取关键信息。"
        "请忽略乱码、导航、页脚和无关模板内容，只保留确认度高的报告信息。"
        '只输出 JSON，对象字段固定为 "title", "speaker", "time", "location", "summary"。'
        "summary 用简体中文，控制在 90 字内，不要捏造。缺失字段填空字符串。"
    )
    user_prompt = (
        f"页面标题：{title}\n"
        f"发布日期：{publish_date}\n"
        f"链接：{detail_url}\n"
        "原文如下：\n"
        f"{cleaned_text[:3000]}"
    )
    result = chat_complete(
        system_prompt,
        user_prompt,
        model=getattr(config, "PHYSICS_EXTRACT_LLM_MODEL", "") or None,
        max_tokens=300,
        temperature=0,
        task_label=f"正在提取学术报告字段：{title[:24]}",
    )
    return _extract_json_block(result or "")


def _build_report_body(title: str, publish_date: str, detail_url: str, cleaned_text: str) -> tuple[str, str]:
    extracted = _extract_report_fields_with_llm(title, publish_date, detail_url, cleaned_text)

    extracted_title = str(extracted.get("title") or "").strip()
    final_title = extracted_title or title
    speaker = str(extracted.get("speaker") or "").strip() or _extract_original_field(cleaned_text, ["报 告 人", "报告人"])
    event_time = str(extracted.get("time") or "").strip() or _extract_original_field(cleaned_text, ["报告时间", "时间"])
    location = str(extracted.get("location") or "").strip() or _extract_original_field(cleaned_text, ["报告地点", "地点"])
    summary = str(extracted.get("summary") or "").strip()
    original_summary = _extract_original_report_summary(cleaned_text)

    body = []
    if publish_date:
        body.append(f"发布日期: {publish_date}")
    if event_time:
        body.append(f"报告时间: {event_time}")
    if location:
        body.append(f"报告地点: {location}")
    if speaker:
        body.append(f"报告人: {speaker}")
    body.append(f"链接: {detail_url}")
    body.append("")
    if original_summary:
        body.append(f"内容摘要：{original_summary}")
    elif summary:
        body.append(f"报告摘要：{summary}")
    else:
        body.append(cleaned_text[:1800])

    return final_title, "\n\n".join(body).strip()


def _extract_original_report_summary(text: str) -> str:
    if not text:
        return ""
    match = re.search(
        r"(?:\*\*)?(?:内容摘要|报告摘要|摘要|Abstract)\s*[：:]?(?:\*\*)?\s*([\s\S]+)$",
        text,
        flags=re.I,
    )
    if not match:
        return ""
    summary = match.group(1).strip()
    summary = re.split(
        r"\n\s*(?:\*\*)?(?:报告题目|报告人简介|报告人|报\s*告\s*人|报告时间|报告地点|上一篇|下一篇|上一条|下一条|关闭窗口|分享到|版权所有)(?:\s*[：:].*)?$",
        summary,
        maxsplit=1,
        flags=re.M,
    )[0].strip()
    summary = re.sub(r"\n{3,}", "\n\n", summary)
    return summary[:1800].strip()


def _extract_original_field(text: str, labels: list[str]) -> str:
    for label in labels:
        pattern = rf"(?:\*\*)?{re.escape(label)}\s*[：:]\s*(?:\*\*)?\s*([^\n]+)"
        match = re.search(pattern, text or "")
        if match:
            value = re.sub(r"\*\*", "", match.group(1)).strip()
            if value:
                return value
    return ""


def _decode_response_text(resp) -> str:
    header_encoding = ""
    content_type = resp.headers.get("Content-Type", "")
    match = re.search(r"charset=([\w-]+)", content_type, flags=re.I)
    if match:
        header_encoding = match.group(1).strip()

    candidates = ["utf-8", "gb18030", header_encoding, resp.encoding, resp.apparent_encoding]
    content = resp.content or b""
    decoded_candidates = []

    for encoding in candidates:
        if not encoding:
            continue
        try:
            text = content.decode(encoding)
        except Exception:
            continue
        decoded_candidates.append(text)

    if decoded_candidates:
        return max(decoded_candidates, key=_text_quality_score)
    return content.decode("utf-8", errors="replace")


class _PhysicsContentParser(HTMLParser):
    TARGET_CLASS_NAMES = ("v_news_content", "wp_articlecontent", "articlecontent")
    TARGET_IDS = ("vsb_content",)

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.candidates = []
        self._capturing = False
        self._depth = 0
        self._buffer = []

    def _is_target(self, attrs) -> bool:
        attr_map = {name.lower(): (value or "") for name, value in attrs}
        element_id = attr_map.get("id", "")
        class_value = attr_map.get("class", "")
        if element_id in self.TARGET_IDS:
            return True
        return any(name in class_value for name in self.TARGET_CLASS_NAMES)

    def _format_start_tag(self, tag, attrs) -> str:
        rendered_attrs = []
        for name, value in attrs:
            if value is None:
                rendered_attrs.append(name)
            else:
                escaped = str(value).replace("&", "&amp;").replace('"', "&quot;")
                rendered_attrs.append(f'{name}="{escaped}"')
        suffix = (" " + " ".join(rendered_attrs)) if rendered_attrs else ""
        return f"<{tag}{suffix}>"

    def handle_starttag(self, tag, attrs):
        if not self._capturing and self._is_target(attrs):
            self._capturing = True
            self._depth = 1
            self._buffer = []
            return
        if self._capturing:
            self._buffer.append(self._format_start_tag(tag, attrs))
            self._depth += 1

    def handle_startendtag(self, tag, attrs):
        if self._capturing:
            start = self._format_start_tag(tag, attrs)
            self._buffer.append(start[:-1] + " />")

    def handle_endtag(self, tag):
        if not self._capturing:
            return
        self._depth -= 1
        if self._depth <= 0:
            self.candidates.append("".join(self._buffer))
            self._capturing = False
            self._buffer = []
            return
        self._buffer.append(f"</{tag}>")

    def handle_data(self, data):
        if self._capturing:
            self._buffer.append(data)

    def handle_entityref(self, name):
        if self._capturing:
            self._buffer.append(f"&{name};")

    def handle_charref(self, name):
        if self._capturing:
            self._buffer.append(f"&#{name};")


def _extract_main_html(html_text: str) -> str:
    parser = _PhysicsContentParser()
    try:
        parser.feed(html_text or "")
    except Exception:
        pass
    if parser.candidates:
        return max(parser.candidates, key=len)

    candidates = []
    patterns = [
        r"<div[^>]+id=[\"']vsb_content[\"'][^>]*>([\s\S]*?)</div>",
        r"<div[^>]+class=[\"'][^\"']*wp_articlecontent[^\"']*[\"'][^>]*>([\s\S]*?)</div>",
        r"<div[^>]+class=[\"'][^\"']*content[^\"']*[\"'][^>]*>([\s\S]*?)</div>",
        r"<article[^>]*>([\s\S]*?)</article>",
    ]
    for pattern in patterns:
        candidates.extend(re.findall(pattern, html_text, flags=re.I))

    if candidates:
        return max(candidates, key=len)

    body_match = re.search(r"<body[^>]*>([\s\S]*?)</body>", html_text, flags=re.I)
    if body_match:
        body_html = body_match.group(1)
        body_html = re.sub(r"<(script|style|nav|header|footer)[^>]*>[\s\S]*?</\1>", "", body_html, flags=re.I)
        return body_html

    return html_text


def _extract_list_date_from_link(link) -> str:
    candidates = []
    try:
        candidates.append((link.text or "").strip())
    except Exception:
        pass
    try:
        parent = link.find_element(By.XPATH, './ancestor::*[self::li or self::tr or self::div][1]')
        candidates.append((parent.text or "").strip())
    except Exception:
        pass
    for text in candidates:
        match = re.search(r"(20\d{2}[\u5e74\-/.]\d{1,2}[\u6708\-/.]\d{1,2}(?:\u65e5)?)", text)
        if match:
            return match.group(1)
    return ""


def crawl_physics(doc, _base_images_dir):
    cutoff = current_issue_cutoff()
    previous_titles = load_previous_titles()
    browser = make_browser()
    titles = []
    full_texts = []
    seen_urls = set()

    try:
        for page_url in config.PHYSICS_REPORT_LIST_PAGES:
            browser.get(page_url)
            session = build_requests_session(browser)
            links = browser.find_elements(By.TAG_NAME, "a")

            for link in links:
                title = ((link.text or "").strip() or (link.get_attribute("title") or "").strip())
                href = (link.get_attribute("href") or "").strip()
                list_date = _extract_list_date_from_link(link)
                if not href:
                    continue
                if href in seen_urls:
                    log_filter_decision(section="physics", title=title, status="dropped", reason="duplicate_url", stage="crawler_physics", date=list_date, url=href)
                    continue
                if not _looks_like_report(title):
                    log_filter_decision(section="physics", title=title, status="dropped", reason="not_report_like", stage="crawler_physics", date=list_date, url=href)
                    continue
                log_filter_decision(section="physics", title=title, status="found", reason="list_item", stage="crawler_physics", date=list_date, url=href)
                if seen_in_previous_issue(title, previous_titles):
                    log_filter_decision(section="physics", title=title, status="dropped", reason="previous_issue", stage="crawler_physics", date=list_date, url=href)
                    continue
                if list_date and should_skip_by_time(list_date, cutoff):
                    log_filter_decision(section="physics", title=title, status="found", reason="list_date_older_than_cutoff_but_detail_checked", stage="crawler_physics", date=list_date, url=href)

                seen_urls.add(href)
                detail_url = urljoin(page_url, href)
                try:
                    resp = session.get(detail_url, timeout=15)
                    resp.raise_for_status()
                except Exception as exc:
                    log_filter_decision(section="physics", title=title, status="error", reason="request_failed", stage="crawler_physics_detail", date=list_date, url=detail_url, details={"error": str(exc)[:300]})
                    continue

                detail_html = _decode_response_text(resp)
                content_text = _normalize_text(_extract_main_html(detail_html))
                if not content_text:
                    log_filter_decision(section="physics", title=title, status="dropped", reason="empty_detail_content", stage="crawler_physics_detail", date=list_date, url=detail_url)
                    continue

                cleaned_text = _clean_physics_text(content_text, title)
                if _looks_like_non_report_page(title, cleaned_text[:600]):
                    log_filter_decision(section="physics", title=title, status="dropped", reason="non_report_page", stage="crawler_physics_detail", date=list_date, url=detail_url)
                    continue
                publish_date = _extract_publish_date(title, cleaned_text or content_text)
                if publish_date and should_skip_by_time(publish_date, cutoff):
                    log_filter_decision(section="physics", title=title, status="found", reason="publish_date_older_than_cutoff_but_report_time_checked", stage="crawler_physics_detail", date=publish_date, url=detail_url)
                if seen_in_previous_issue(title, previous_titles):
                    log_filter_decision(section="physics", title=title, status="dropped", reason="previous_issue", stage="crawler_physics_detail", date=publish_date, url=detail_url)
                    continue

                location_hit = any(
                    keyword.lower() in (content_text or "").lower()
                    for keyword in _config_keywords("PHYSICS_REPORT_LOCATION_KEYWORDS", DEFAULT_LOCATION_KEYWORDS)
                )
                decision = True if getattr(config, "RAW_COLLECTION_MODE", False) else resolve_copy_decision("physics", title, publish_date, (content_text or "")[:500])
                if not decision and not location_hit and not _looks_like_report((cleaned_text or content_text)[:200]):
                    log_filter_decision(section="physics", title=title, status="dropped", reason="copy_decision_false", stage="crawler_physics_detail", date=publish_date, url=detail_url)
                    continue

                final_title, body_text = _build_report_body(title, publish_date, detail_url, cleaned_text or content_text)
                titles.append(final_title)
                full_texts.append(body_text)
                log_filter_decision(section="physics", title=title, status="kept", reason="crawler_selected", stage="crawler_physics_detail", date=publish_date, url=detail_url)
    finally:
        browser.quit()

    if not titles:
        print("物理系学术报告：本期时间窗口内没有新增报告")
        return

    doc.write("# 物理系学术报告\n\n")
    save_content(titles, full_texts, doc)
