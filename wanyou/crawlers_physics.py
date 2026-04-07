import re
import json
from urllib.parse import urljoin

import html2text
from selenium.webdriver.common.by import By

import config
from wanyou.decider import resolve_copy_decision
from wanyou.utils_dates import days_since_date
from wanyou.utils_html import save_content
from wanyou.utils_llm import chat_complete
from wanyou.utils_web import build_requests_session, make_browser


def _looks_like_report(title: str) -> bool:
    text = (title or "").strip()
    if not text:
        return False
    keywords = list(config.PHYSICS_REPORT_FORCE_KEYWORDS) + list(config.PHYSICS_REPORT_LOCATION_KEYWORDS)
    return any(keyword.lower() in text.lower() for keyword in keywords if keyword)


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
    keywords = len(re.findall(r"报告|题目|报告人|时间|地点|摘要|简介|物理楼", text))
    mojibake = len(re.findall(r"[\u00c0-\u00ff]{2,}|�|ï»¿", text))
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
        line = line.replace("内 容摘要", "内容摘要")
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
        cleaned = cleaned[min(start_positions) :]

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
        cleaned = cleaned[: min(end_positions)]

    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


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
        max_tokens=300,
        temperature=0,
    )
    return _extract_json_block(result or "")


def _build_report_body(title: str, publish_date: str, detail_url: str, cleaned_text: str) -> tuple[str, str]:
    extracted = _extract_report_fields_with_llm(title, publish_date, detail_url, cleaned_text)

    extracted_title = str(extracted.get("title") or "").strip()
    if title and "：" in title and extracted_title and extracted_title in title:
        final_title = title
    else:
        final_title = extracted_title or title
    speaker = str(extracted.get("speaker") or "").strip()
    event_time = str(extracted.get("time") or "").strip()
    location = str(extracted.get("location") or "").strip()
    summary = str(extracted.get("summary") or "").strip()

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
    if summary:
        body.append(f"报告摘要：{summary}")
    else:
        body.append(cleaned_text[:1800])

    return final_title, "\n\n".join(body).strip()


def _decode_response_text(resp) -> str:
    header_encoding = ""
    content_type = resp.headers.get("Content-Type", "")
    match = re.search(r"charset=([\w-]+)", content_type, flags=re.I)
    if match:
        header_encoding = match.group(1).strip()

    candidates = [header_encoding, resp.encoding, resp.apparent_encoding, "utf-8", "gb18030"]
    content = resp.content or b""

    for encoding in candidates:
        if not encoding:
            continue
        try:
            text = content.decode(encoding)
        except Exception:
            continue
        if "\ufffd" not in text and not re.search(r"[\u00c0-\u00ff]{4,}", text):
            return text

    return content.decode("utf-8", errors="replace")


def _extract_main_html(html_text: str) -> str:
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


def _extract_date(text: str) -> str:
    match = re.search(r"(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2})", text)
    if not match:
        return ""
    date_text = match.group(1)
    date_text = date_text.replace("年", "-").replace("月", "-").replace("日", "")
    date_text = date_text.replace("/", "-").replace(".", "-")
    parts = [part.zfill(2) if index else part for index, part in enumerate(date_text.split("-"))]
    if len(parts) >= 3:
        return "-".join(parts[:3])
    return ""


def crawl_physics(doc, _base_images_dir):
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
                if not href or href in seen_urls or not _looks_like_report(title):
                    continue

                seen_urls.add(href)
                detail_url = urljoin(page_url, href)
                try:
                    resp = session.get(detail_url, timeout=15)
                    resp.raise_for_status()
                except Exception:
                    continue

                detail_html = _decode_response_text(resp)
                content_text = _normalize_text(_extract_main_html(detail_html))
                if not content_text:
                    continue

                cleaned_text = _clean_physics_text(content_text, title)
                publish_date = _extract_publish_date(title, cleaned_text or content_text)
                date = publish_date
                if date:
                    try:
                        if days_since_date(date) > config.PHYSICS_REPORT_RECENT_DAYS:
                            continue
                    except Exception:
                        pass

                location_hit = any(
                    keyword.lower() in content_text.lower()
                    for keyword in config.PHYSICS_REPORT_LOCATION_KEYWORDS
                    if keyword
                )
                decision = resolve_copy_decision("physics", title, date, content_text[:500])
                if not decision and not location_hit and not _looks_like_report((cleaned_text or content_text)[:200]):
                    continue

                final_title, body_text = _build_report_body(title, publish_date, detail_url, cleaned_text or content_text)
                titles.append(final_title)
                full_texts.append(body_text)
    finally:
        browser.quit()

    if not titles:
        return

    doc.write("# 物理系学术报告\n\n")
    save_content(titles, full_texts, doc)
