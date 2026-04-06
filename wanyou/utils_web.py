import requests
from selenium import webdriver
from selenium.webdriver.edge.options import Options

import config


def make_browser():
    options = Options()
    if config.HEADLESS:
        options.add_argument("--headless=new")
    browser = webdriver.Edge(options=options)
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
