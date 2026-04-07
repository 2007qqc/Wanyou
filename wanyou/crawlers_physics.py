import re
from urllib.parse import urljoin

import html2text
from selenium.webdriver.common.by import By

import config
from wanyou.decider import resolve_copy_decision
from wanyou.utils_dates import days_since_date
from wanyou.utils_html import save_content
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
    text = handler.handle(html_text or "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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

                content_text = _normalize_text(resp.text)
                if not content_text:
                    continue

                date = _extract_date(content_text)
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
                if not decision and not location_hit and not _looks_like_report(content_text[:200]):
                    continue

                body = []
                if date:
                    body.append(f"日期: {date}")
                body.append(f"链接: {detail_url}")
                if location_hit:
                    body.append("地点提示: 命中物理系重点地点关键词。")
                body.append("")
                body.append(content_text[:4000])

                titles.append(title)
                full_texts.append("\n\n".join(body).strip())
    finally:
        browser.quit()

    if not titles:
        return

    doc.write("# 物理系学术报告\n\n")
    save_content(titles, full_texts, doc)
