import os
import tempfile
from pathlib import Path

import requests

import config
from wanyou.browser import browser_supports_profile_dir, get_selenium_browser_name, make_browser_options, make_webdriver


def make_browser(headless=None):
    os.makedirs(config.SELENIUM_CACHE_DIR, exist_ok=True)
    os.environ.setdefault("SE_CACHE_PATH", os.path.abspath(config.SELENIUM_CACHE_DIR))
    browser_name = get_selenium_browser_name()
    profile_dir = ""
    if browser_supports_profile_dir(browser_name):
        profile_dir = tempfile.mkdtemp(
            prefix=f"{browser_name}-profile-",
            dir=os.path.abspath(config.SELENIUM_CACHE_DIR),
        )
    use_headless = config.HEADLESS if headless is None else bool(headless)
    options = make_browser_options(browser_name, profile_dir, headless=use_headless)
    browser = make_webdriver(browser_name, options)
    if profile_dir:
        browser._codex_profile_dir = profile_dir
    browser._wanyou_browser_name = browser_name
    if config.PAGE_LOAD_TIMEOUT:
        browser.set_page_load_timeout(config.PAGE_LOAD_TIMEOUT)
    return browser


def build_requests_session(browser):
    session = requests.Session()
    for cookie in browser.get_cookies():
        session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"))
    session.headers.update({"User-Agent": config.USER_AGENT})
    return session


def open_in_new_tab(url, seen_urls, browser, base_window):
    seen_urls.add(url)
    browser.execute_script("window.open(arguments[0]);", url)
    target = browser.window_handles[0]
    if target == base_window:
        target = browser.window_handles[1]
    browser.switch_to.window(target)
    return seen_urls, browser


def dump_browser_snapshot(browser, output_dir, name):
    if not output_dir:
        return
    try:
        debug_dir = Path(output_dir)
        debug_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name).strip("._") or "snapshot"
        (debug_dir / f"{safe_name}.txt").write_text(
            "\n".join(
                [
                    f"URL: {getattr(browser, 'current_url', '')}",
                    f"TITLE: {getattr(browser, 'title', '')}",
                ]
            ),
            encoding="utf-8",
        )
        page_source = getattr(browser, "page_source", "") or ""
        (debug_dir / f"{safe_name}.html").write_text(page_source, encoding="utf-8")
    except Exception:
        pass
