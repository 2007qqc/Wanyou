import os
import re
import time

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import config
from wanyou.decider import resolve_copy_decision
from wanyou.unified_auth import authenticate_shared_browser
from wanyou.utils_issue_filter import current_issue_cutoff, load_previous_titles, seen_in_previous_issue, should_skip_by_time
from wanyou.utils_html import html_to_markdown, save_content
from wanyou.utils_ocr import convert_markdown_images_to_text
from wanyou.utils_web import build_requests_session, dump_browser_snapshot, open_in_new_tab


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
            return WebDriverWait(browser, wait_timeout).until(
                EC.presence_of_element_located((by, value))
            )
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise TimeoutException("No selector matched in wait_and_find")


def _find_notice_links(browser):
    selectors = [
        (By.XPATH, "//a[contains(@href, 'News_notice_Detail.aspx')]"),
        (By.CSS_SELECTOR, "a[href*='News_notice_Detail.aspx']"),
        (By.CSS_SELECTOR, "a[target='_blank'][href*='News_notice_Detail']"),
        (By.CSS_SELECTOR, "a[href*='notice']"),
    ]
    for by, value in selectors:
        try:
            links = browser.find_elements(by, value)
        except Exception:
            continue
        usable = [link for link in links if (link.get_attribute("href") or "").strip()]
        if usable:
            return usable
    return []




def _extract_list_date(link):
    candidates = []
    try:
        candidates.append((link.text or "").strip())
    except Exception:
        pass
    try:
        parent = link.find_element(By.XPATH, './ancestor::tr[1]')
        candidates.append((parent.text or "").strip())
    except Exception:
        pass
    for text in candidates:
        match = re.search(r"(20\d{2})\D(\d{1,2})\D(\d{1,2})", text)
        if match:
            return f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
    return ""

def _extract_detail_date(browser):
    selectors = [
        (By.ID, "News_notice_DetailCtrl1_lbladd_time"),
        (By.CSS_SELECTOR, "#News_notice_DetailCtrl1_lbladd_time"),
        (By.CSS_SELECTOR, "[id*='lbladd_time']"),
        (By.CSS_SELECTOR, ".date"),
        (By.CSS_SELECTOR, "[class*='date']"),
    ]
    text = (_find_first(browser, selectors).text or "").strip()
    match = re.search(r"(20\d{2})\D(\d{1,2})\D(\d{1,2})", text)
    if not match:
        raise NoSuchElementException("myhome detail date not found")
    return f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"


def _extract_detail_title(browser):
    selectors = [
        (By.ID, "News_notice_DetailCtrl1_lblTitle"),
        (By.CSS_SELECTOR, "#News_notice_DetailCtrl1_lblTitle"),
        (By.CSS_SELECTOR, "h1"),
        (By.CSS_SELECTOR, "[class*='title']"),
    ]
    text = (_find_first(browser, selectors).text or "").strip()
    if not text:
        raise NoSuchElementException("myhome detail title not found")
    return text


def _extract_detail_container(browser):
    selectors = [
        (
            By.XPATH,
            "//td[@class='content1 content2' and @colspan='2' and contains(@style, 'text-align: left')]",
        ),
        (By.CSS_SELECTOR, "td.content1.content2[colspan='2']"),
        (By.CSS_SELECTOR, ".content1.content2"),
        (By.CSS_SELECTOR, ".content"),
        (By.CSS_SELECTOR, "[class*='content']"),
    ]
    return _wait_and_find(browser, selectors)


def crawl_myhome(doc, base_images_dir, username="", password="", browser=None):
    debug_dir = os.path.join(os.path.dirname(base_images_dir), "debug")
    owns_browser = browser is None
    if browser is None:
        browser = authenticate_shared_browser(username, password, debug_dir, config.URL_MYHOME, stage_label="家园网")

    try:
        print("成功登录家园网，正在获取信息")
        browser.get(config.URL_MYHOME)
        dump_browser_snapshot(browser, debug_dir, "myhome_after_login")
        print("已进入家园网页面，正在读取通知列表")
        session = build_requests_session(browser)

        notice_links = _find_notice_links(browser)
        if not notice_links:
            dump_browser_snapshot(browser, debug_dir, "myhome_no_notice_links")
            raise RuntimeError("家园网页未发现通知入口，可能是登录未生效或页面结构已变更")

        cutoff = current_issue_cutoff()
        previous_titles = load_previous_titles()
        seen_urls = set()
        web = browser.window_handles[0]
        time.sleep(1)

        titles = []
        full_texts = []
        image_counter = [0]
        inline_images_dir = os.path.join(base_images_dir, "inline")

        for link in notice_links:
            try:
                url = (link.get_attribute("href") or "").strip()
                list_title = (link.text or "").strip()
                list_date = _extract_list_date(link)
                if not url or url in seen_urls:
                    continue
                if list_title and seen_in_previous_issue(list_title, previous_titles):
                    continue
                if list_date and should_skip_by_time(list_date, cutoff):
                    continue

                seen_urls, browser = open_in_new_tab(url, seen_urls, browser, web)
                date = _extract_detail_date(browser)
                if should_skip_by_time(date, cutoff):
                    browser.close()
                    browser.switch_to.window(web)
                    continue

                title = _extract_detail_title(browser)
                if seen_in_previous_issue(title, previous_titles):
                    browser.close()
                    browser.switch_to.window(web)
                    continue
                if any(sub in title for sub in config.MYHOME_NO_CONSIDER):
                    browser.close()
                    browser.switch_to.window(web)
                    continue

                decision = resolve_copy_decision("myhome", title, date)
                if decision:
                    container = _extract_detail_container(browser)
                    content_md = html_to_markdown(
                        container,
                        browser.current_url,
                        session,
                        inline_images_dir,
                        image_counter,
                        "myhome",
                        browser.current_url,
                    )
                    content_md = convert_markdown_images_to_text(content_md)
                    titles.append(title)
                    full_texts.append(content_md)

                browser.close()
                browser.switch_to.window(web)
            except Exception:
                try:
                    if len(browser.window_handles) > 1:
                        browser.close()
                        browser.switch_to.window(web)
                except Exception:
                    pass
                continue

        if not titles:
            dump_browser_snapshot(browser, debug_dir, "myhome_no_titles")
            raise RuntimeError("家园网抓取完成但未获得有效通知，可能是筛选条件过严或详情页选择器失效")

        print(f"家园网信息抓取完成，共获取 {len(titles)} 条")
        doc.write("# 家园网信息\n\n")
        save_content(titles, full_texts, doc)
    finally:
        if owns_browser:
            browser.quit()
