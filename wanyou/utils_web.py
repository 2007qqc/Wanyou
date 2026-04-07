import os
import tempfile
from pathlib import Path

import requests
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service

import config


def make_browser():
    os.makedirs(config.SELENIUM_CACHE_DIR, exist_ok=True)
    os.environ.setdefault("SE_CACHE_PATH", os.path.abspath(config.SELENIUM_CACHE_DIR))
    profile_dir = tempfile.mkdtemp(prefix="edge-profile-", dir=os.path.abspath(config.SELENIUM_CACHE_DIR))
    options = Options()
    options.page_load_strategy = getattr(config, "PAGE_LOAD_STRATEGY", "eager")
    if config.HEADLESS:
        options.add_argument("--headless")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-logging")
    options.add_argument("--silent")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-default-apps")
    options.add_argument("--remote-debugging-pipe")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--allow-insecure-localhost")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-component-update")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-features=msEdgeSidebarV2,EdgeWalletCheckout,msPdfAadIntegration")
    options.add_argument(f"--user-data-dir={profile_dir}")
    try:
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
    except Exception:
        pass
    service = Service(log_output=os.devnull)
    browser = webdriver.Edge(options=options, service=service)
    browser._codex_profile_dir = profile_dir
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
