import os
import re
import time

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import config
from wanyou.decider import resolve_copy_decision
from wanyou.filter_debug import log_filter_decision
from wanyou.unified_auth import authenticate_shared_browser
from wanyou.utils_html import html_to_markdown, save_content
from wanyou.utils_issue_filter import load_previous_titles, seen_in_previous_issue
from wanyou.utils_llm import chat_complete
from wanyou.utils_web import build_requests_session, dump_browser_snapshot, open_in_new_tab

TEACHING_FALLBACK_KEYWORDS = ["教务", "课程", "选课", "退课", "考试", "学籍", "培养", "本科生", "研究生", "成绩", "补退", "重修", "SRT"]

def _find_first(browser, selectors):
    for by, value in selectors:
        try:
            return browser.find_element(by, value)
        except Exception:
            continue
    raise NoSuchElementException(f"Unable to locate any selector from: {selectors}")

def _wait_and_find(browser, selectors, timeout=None):
    wait_timeout = timeout or config.WAIT_TIMEOUT
    last_error = None
    for by, value in selectors:
        try:
            return WebDriverWait(browser, wait_timeout).until(EC.presence_of_element_located((by, value)))
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise TimeoutException("No selector matched in wait_and_find")

def _find_notice_blocks(browser, extra_selectors=None):
    selectors = [
        (By.CSS_SELECTOR, "div.you"), (By.CSS_SELECTOR, ".you"), (By.CSS_SELECTOR, "div.notice-item"),
        (By.CSS_SELECTOR, "li.notice-item"), (By.CSS_SELECTOR, "div[class*='notice']"),
        (By.CSS_SELECTOR, "li[class*='notice']"), (By.CSS_SELECTOR, "#liebiaotml > div"),
        (By.CSS_SELECTOR, "#liebiaotml > li"), (By.CSS_SELECTOR, "#liebiaotml a"),
    ]
    for selector in extra_selectors or []:
        if isinstance(selector, (list, tuple)) and len(selector) == 2:
            selectors.insert(0, (selector[0], selector[1]))
    for by, value in selectors:
        try:
            blocks = browser.find_elements(by, value)
        except Exception:
            continue
        usable = [block for block in blocks if (block.text or "").strip() or block.get_attribute("href")]
        if usable:
            return usable
    return []

def _extract_block_link(block):
    selectors = [(By.CSS_SELECTOR, "div.title > a"), (By.CSS_SELECTOR, ".title a"), (By.CSS_SELECTOR, "a[title]"), (By.TAG_NAME, "a")]
    if (block.get_attribute("href") or "").strip():
        href = (block.get_attribute("href") or "").strip()
        return block, href
    for by, value in selectors:
        try:
            link = block.find_element(by, value)
            href = (link.get_attribute("href") or "").strip()
            if href:
                return link, href
        except Exception:
            continue
    raise NoSuchElementException("notice block has no usable link")

def _extract_detail_date(browser):
    selectors = [(By.ID, "timeFlag"), (By.CSS_SELECTOR, "#timeFlag span"), (By.CSS_SELECTOR, ".time span"), (By.CSS_SELECTOR, ".date"), (By.CSS_SELECTOR, "[class*='time']")]
    node = _find_first(browser, selectors)
    text = (node.text or "").strip()
    if len(text) >= 10:
        return text[:10]
    raise NoSuchElementException("detail page date not found")

def _extract_detail_title(browser):
    selectors = [(By.CLASS_NAME, "title"), (By.CSS_SELECTOR, "h1"), (By.CSS_SELECTOR, ".article-title"), (By.CSS_SELECTOR, "[class*='title']")]
    node = _find_first(browser, selectors)
    text = (node.text or "").strip()
    if text:
        return text
    raise NoSuchElementException("detail page title not found")

def _extract_detail_container(browser):
    selectors = [(By.CLASS_NAME, "xiangqingchakan"), (By.CSS_SELECTOR, ".xiangqingchakan"), (By.CSS_SELECTOR, ".content"), (By.CSS_SELECTOR, ".article-content"), (By.CSS_SELECTOR, "[class*='detail']")]
    return _wait_and_find(browser, selectors)

def _open_teaching_section(browser):
    selectors = [(By.ID, "LM_JWGG"), (By.CSS_SELECTOR, "[id='LM_JWGG']"), (By.XPATH, "//*[@id='LM_JWGG']"), (By.XPATH, "//a[contains(normalize-space(.), '教务')]"), (By.XPATH, "//button[contains(normalize-space(.), '教务')]"), (By.XPATH, "//*[contains(@class,'menu') and contains(normalize-space(.), '教务')]")]
    tab = _wait_and_find(browser, selectors)
    browser.execute_script("arguments[0].click();", tab)
    try:
        browser.execute_script("if (typeof golm_func === 'function') { golm_func('LM_JWGG'); }")
    except Exception:
        pass

def _page_shows_no_data(browser):
    selectors = [(By.ID, "getmore1"), (By.CSS_SELECTOR, ".wushuju"), (By.CSS_SELECTOR, ".nulltag")]
    for by, value in selectors:
        try:
            text = " ".join((node.text or "").strip() for node in browser.find_elements(by, value))
        except Exception:
            continue
        if "暂无数据" in text:
            return True
    return False

def _info_url_with_lmid(base_url: str, lmid: str) -> str:
    if "lmid=" in base_url:
        return re.sub(r"lmid=[^&]+", f"lmid={lmid}", base_url)
    joiner = "&" if "?" in base_url else "?"
    return f"{base_url}{joiner}lmid={lmid}"

def _looks_like_teaching_title(title: str) -> bool:
    text = (title or "").strip().lower()
    return any(keyword.lower() in text for keyword in TEACHING_FALLBACK_KEYWORDS)

def _write_info_llm_hint(debug_dir, browser, session):
    try:
        script_sources = browser.execute_script("return Array.from(document.scripts).map(s => s.src).filter(Boolean);")
    except Exception:
        script_sources = []
    interesting_scripts = []
    for src in script_sources:
        if not any(key in src for key in ["xxfb", "template", "info"]):
            continue
        try:
            resp = session.get(src, timeout=10)
            resp.raise_for_status()
            interesting_scripts.append(f"URL: {src}\n{resp.text[:5000]}")
        except Exception:
            continue
        if len(interesting_scripts) >= 2:
            break
    page_html = (browser.page_source or "")[:8000]
    result = chat_complete(
        "You are diagnosing a campus notice page. The current page has already activated the 教务通知 tab but the list is empty. Read the HTML and JS snippets and output compact JSON with keys selectors, calls, diagnosis. Only output JSON.",
        f"HTML:\n{page_html}\n\nJS:\n{chr(10).join(interesting_scripts)[:9000]}",
        max_tokens=300,
        temperature=0,
        task_label="正在分析教务页面结构",
    )
    if result:
        os.makedirs(debug_dir, exist_ok=True)
        with open(os.path.join(debug_dir, "info_llm_hint.json"), "w", encoding="utf-8") as f:
            f.write(result)

def _collect_info_items(browser, session, base_images_dir, title_filter=None):
    previous_titles = load_previous_titles()
    seen_urls = set()
    web = browser.window_handles[0]
    titles = []
    full_texts = []
    image_counter = [0]
    inline_images_dir = os.path.join(base_images_dir, "inline")
    for block in _find_notice_blocks(browser):
        try:
            link_node, url = _extract_block_link(block)
            list_title = ((link_node.text or "").strip() or (block.text or "").strip().splitlines()[0].strip())
            log_filter_decision(section="info", title=list_title, status="found", reason="list_item", stage="crawler_info", url=url)
            if url in seen_urls:
                log_filter_decision(section="info", title=list_title, status="dropped", reason="duplicate_url", stage="crawler_info", url=url)
                continue
            if list_title and seen_in_previous_issue(list_title, previous_titles):
                log_filter_decision(section="info", title=list_title, status="dropped", reason="previous_issue", stage="crawler_info", url=url)
                continue
            seen_urls, browser = open_in_new_tab(url, seen_urls, browser, web)
            time.sleep(2)
            date = _extract_detail_date(browser)
            title = _extract_detail_title(browser)
            if seen_in_previous_issue(title, previous_titles):
                log_filter_decision(section="info", title=title, status="dropped", reason="previous_issue", stage="crawler_info_detail", date=date, url=browser.current_url)
                browser.close(); browser.switch_to.window(web); continue
            if (not getattr(config, "RAW_COLLECTION_MODE", False)) and title_filter and not title_filter(title):
                log_filter_decision(section="info", title=title, status="dropped", reason="title_filter", stage="crawler_info_detail", date=date, url=browser.current_url)
                browser.close(); browser.switch_to.window(web); continue
            if getattr(config, "RAW_COLLECTION_MODE", False) or resolve_copy_decision("info", title, date):
                container = _extract_detail_container(browser)
                titles.append(title)
                full_texts.append(html_to_markdown(container, browser.current_url, session, inline_images_dir, image_counter, "info", browser.current_url))
                log_filter_decision(section="info", title=title, status="kept", reason="crawler_selected", stage="crawler_info_detail", date=date, url=browser.current_url)
            else:
                log_filter_decision(section="info", title=title, status="dropped", reason="copy_decision_false", stage="crawler_info_detail", date=date, url=browser.current_url)
            browser.close(); browser.switch_to.window(web)
        except Exception as exc:
            try:
                log_filter_decision(section="info", title=locals().get("list_title") or locals().get("title") or "", status="error", reason="detail_exception", stage="crawler_info", url=locals().get("url") or "", details={"error": str(exc)[:300]})
            except Exception:
                pass
            try:
                if len(browser.window_handles) > 1:
                    browser.close(); browser.switch_to.window(web)
            except Exception:
                pass
            continue
    return titles, full_texts

def crawl_info(doc, base_images_dir, username="", password="", browser=None):
    debug_dir = os.path.join(os.path.dirname(base_images_dir), "debug")
    owns_browser = browser is None
    if browser is None:
        browser = authenticate_shared_browser(username, password, debug_dir, config.URL_INFO, stage_label="教务")
    try:
        print("成功登录教务，正在获取信息")
        browser.get(config.URL_INFO)
        dump_browser_snapshot(browser, debug_dir, "info_after_login")
        print("已进入教务页面，正在定位教务通知入口")
        session = build_requests_session(browser)
        try:
            _open_teaching_section(browser)
            time.sleep(2)
            dump_browser_snapshot(browser, debug_dir, "info_after_open_teaching")
            print("已打开教务通知栏目，正在读取列表")
        except Exception:
            pass
        titles, full_texts = _collect_info_items(browser, session, base_images_dir)
        if not titles and _page_shows_no_data(browser):
            for lmid, title_filter, debug_name in [("LM_JWGG", None, "info_direct_jwgg"), ("LM_ZJQRXXHZ", _looks_like_teaching_title, "info_recent_summary"), ("all", _looks_like_teaching_title, "info_all_sections")]:
                print(f"教务主列表为空，正在尝试备用入口 {lmid}")
                browser.get(_info_url_with_lmid(config.URL_INFO, lmid))
                time.sleep(2)
                dump_browser_snapshot(browser, debug_dir, debug_name)
                extra_titles, extra_texts = _collect_info_items(browser, session, base_images_dir, title_filter=title_filter)
                if extra_titles:
                    titles, full_texts = extra_titles, extra_texts
                    break
        if not titles:
            dump_browser_snapshot(browser, debug_dir, "info_no_notice_blocks")
            _write_info_llm_hint(debug_dir, browser, session)
            raise RuntimeError("教务通知页已打开，但列表为空或前端接口未返回数据，需要继续适配新版页面")
        print(f"教务信息抓取完成，共获取 {len(titles)} 条")
        doc.write("# 教务通知\n\n")
        save_content(titles, full_texts, doc)
    finally:
        if owns_browser:
            browser.quit()
