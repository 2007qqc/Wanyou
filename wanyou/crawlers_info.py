import os
import time
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException

import config
from wanyou.utils_dates import days_since_date
from wanyou.utils_web import make_browser, build_requests_session, dump_browser_snapshot, open_in_new_tab
from wanyou.utils_html import html_to_markdown, save_content
from wanyou.decider import resolve_copy_decision


def _find_notice_blocks(browser):
    selectors = [
        (By.CSS_SELECTOR, "div.you"),
        (By.CSS_SELECTOR, ".you"),
        (By.CSS_SELECTOR, "div.notice-item"),
        (By.CSS_SELECTOR, "li.notice-item"),
        (By.CSS_SELECTOR, "div[class*='notice']"),
        (By.CSS_SELECTOR, "li[class*='notice']"),
    ]
    for by, value in selectors:
        try:
            blocks = browser.find_elements(by, value)
        except Exception:
            continue
        if blocks:
            return blocks
    return []


def _extract_block_link(block):
    selectors = [
        (By.CSS_SELECTOR, "div.title > a"),
        (By.CSS_SELECTOR, ".title a"),
        (By.CSS_SELECTOR, "a[title]"),
        (By.TAG_NAME, "a"),
    ]
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
    selectors = [
        (By.ID, "timeFlag"),
        (By.CSS_SELECTOR, "#timeFlag span"),
        (By.CSS_SELECTOR, ".time span"),
        (By.CSS_SELECTOR, ".date"),
        (By.CSS_SELECTOR, "[class*='time']"),
    ]
    node = _find_first(browser, selectors)
    text = (node.text or "").strip()
    if len(text) >= 10:
        return text[:10]
    raise NoSuchElementException("detail page date not found")


def _extract_detail_title(browser):
    selectors = [
        (By.CLASS_NAME, "title"),
        (By.CSS_SELECTOR, "h1"),
        (By.CSS_SELECTOR, ".article-title"),
        (By.CSS_SELECTOR, "[class*='title']"),
    ]
    node = _find_first(browser, selectors)
    text = (node.text or "").strip()
    if text:
        return text
    raise NoSuchElementException("detail page title not found")


def _extract_detail_container(browser):
    selectors = [
        (By.CLASS_NAME, "xiangqingchakan"),
        (By.CSS_SELECTOR, ".xiangqingchakan"),
        (By.CSS_SELECTOR, ".content"),
        (By.CSS_SELECTOR, ".article-content"),
        (By.CSS_SELECTOR, "[class*='detail']"),
    ]
    return _wait_and_find(browser, selectors)


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


def _open_teaching_section(browser):
    selectors = [
        (By.ID, "LM_JWGG"),
        (By.CSS_SELECTOR, "[id='LM_JWGG']"),
        (By.XPATH, "//*[@id='LM_JWGG']"),
        (By.XPATH, "//a[contains(normalize-space(.), '教务')]"),
        (By.XPATH, "//button[contains(normalize-space(.), '教务')]"),
        (By.XPATH, "//*[contains(@class,'menu') and contains(normalize-space(.), '教务')]"),
    ]
    tab = _wait_and_find(browser, selectors)
    browser.execute_script("arguments[0].click();", tab)


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


def crawl_info(doc, base_images_dir, username, password):
    browser = make_browser()
    debug_dir = os.path.join(os.path.dirname(base_images_dir), "debug")
    browser.get(config.URL_INFO)
    button = _find_first(browser, [(By.ID, "i_user"), (By.NAME, "username"), (By.CSS_SELECTOR, "input[type='text']")])
    button.send_keys(username)
    button = _find_first(browser, [(By.ID, "i_pass"), (By.NAME, "password"), (By.CSS_SELECTOR, "input[type='password']")])
    button.send_keys(password)
    button = _find_first(
        browser,
        [
            (By.CSS_SELECTOR, "a.btn.btn-lg.btn-primary.btn-block"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(normalize-space(.), '登录')]"),
            (By.XPATH, "//a[contains(normalize-space(.), '登录')]"),
        ],
    )
    button.click()
    time.sleep(config.SLEEP_SECONDS)

    browser.get(config.URL_INFO)
    dump_browser_snapshot(browser, debug_dir, "info_after_login")
    if _looks_like_login_page(browser):
        browser.quit()
        raise RuntimeError("教务登录未通过，请检查该站点的用户名和密码是否正确")
    print("教务登录成功，开始抓取通知")
    session = build_requests_session(browser)

    try:
        _open_teaching_section(browser)
        time.sleep(1)
        dump_browser_snapshot(browser, debug_dir, "info_after_open_teaching")
    except Exception:
        pass

    notice_blocks = _find_notice_blocks(browser)
    if not notice_blocks:
        dump_browser_snapshot(browser, debug_dir, "info_no_notice_blocks")
        browser.quit()
        raise RuntimeError("教务页未发现通知列表，可能是登录未生效或栏目入口已变更")
    seen_urls = set()
    web = browser.window_handles[0]

    titles = []
    full_texts = []
    image_counter = [0]
    inline_images_dir = os.path.join(base_images_dir, "inline")

    for block in notice_blocks:
        try:
            try:
                block.find_element(By.CSS_SELECTOR, '.icon.iconfont.icon-a-14.zhidi')
                up = False
            except NoSuchElementException:
                up = True
            link, url = _extract_block_link(block)

            if url not in seen_urls:
                seen_urls, browser = open_in_new_tab(url, seen_urls, browser, web)

                time.sleep(2)
                date = _extract_detail_date(browser)

                if (days_since_date(date) > config.DAYS_WINDOW_INFO) & up:
                    break

                title = _extract_detail_title(browser)
                decision = resolve_copy_decision("info", title, date)
                if decision:
                    container = _extract_detail_container(browser)
                    titles.append(title)
                    full_texts.append(
                        html_to_markdown(
                            container,
                            browser.current_url,
                            session,
                            inline_images_dir,
                            image_counter,
                            "info",
                            browser.current_url,
                        )
                    )

                browser.close()
                browser.switch_to.window(web)

        except Exception:
            continue

    if not titles:
        dump_browser_snapshot(browser, debug_dir, "info_no_titles")
        browser.quit()
        raise RuntimeError("教务抓取完成但未获得有效通知，可能是筛选条件过严或详情页选择器失效")
    browser.quit()
    doc.write("# 教务通知\n\n")
    save_content(titles, full_texts, doc)
