import os
import re
import time

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import config
from wanyou.decider import resolve_copy_decision
from wanyou.utils_dates import days_since_date
from wanyou.utils_html import html_to_markdown, save_content
from wanyou.utils_ocr import convert_markdown_images_to_text
from wanyou.utils_web import build_requests_session, dump_browser_snapshot, make_browser, open_in_new_tab


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


def _login(browser, username, password):
    browser.get(config.URL_MYHOME)
    _find_first(
        browser,
        [
            (By.ID, "i_user"),
            (By.NAME, "username"),
            (By.CSS_SELECTOR, "input[type='text']"),
        ],
    ).send_keys(username)
    _find_first(
        browser,
        [
            (By.ID, "i_pass"),
            (By.NAME, "password"),
            (By.CSS_SELECTOR, "input[type='password']"),
        ],
    ).send_keys(password)
    _find_first(
        browser,
        [
            (By.CSS_SELECTOR, "a.btn.btn-lg.btn-primary.btn-block"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(normalize-space(.), '登录')]"),
            (By.XPATH, "//a[contains(normalize-space(.), '登录')]"),
        ],
    ).click()
    time.sleep(config.SLEEP_SECONDS)


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


def _looks_like_login_page(browser):
    selectors = [
        (By.ID, "i_user"),
        (By.ID, "i_pass"),
        (By.NAME, "username"),
        (By.NAME, "password"),
        (By.CSS_SELECTOR, "input[type='password']"),
    ]
    for by, value in selectors:
        try:
            if browser.find_elements(by, value):
                return True
        except Exception:
            continue
    return False


def crawl_myhome(doc, base_images_dir, username, password):
    browser = make_browser()
    debug_dir = os.path.join(os.path.dirname(base_images_dir), "debug")
    try:
        _login(browser, username, password)
        browser.get(config.URL_MYHOME)
        dump_browser_snapshot(browser, debug_dir, "myhome_after_login")
        if _looks_like_login_page(browser):
            raise RuntimeError("家园网登录未通过，请检查该站点的用户名和密码是否正确")
        print("家园网登录成功，开始抓取通知")
        session = build_requests_session(browser)

        notice_links = _find_notice_links(browser)
        if not notice_links:
            dump_browser_snapshot(browser, debug_dir, "myhome_no_notice_links")
            raise RuntimeError("家园网页未发现通知入口，可能是登录未生效或页面结构已变更")

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
                if not url or url in seen_urls:
                    continue

                seen_urls, browser = open_in_new_tab(url, seen_urls, browser, web)
                date = _extract_detail_date(browser)
                if days_since_date(date) > config.DAYS_WINDOW_MYHOME:
                    browser.close()
                    browser.switch_to.window(web)
                    continue

                title = _extract_detail_title(browser)
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

        doc.write("# 家园网信息\n\n")
        save_content(titles, full_texts, doc)
    finally:
        browser.quit()
