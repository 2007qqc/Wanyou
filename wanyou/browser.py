import os

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService

import config


SUPPORTED_BROWSERS = {"chrome", "edge"}


def get_selenium_browser_name() -> str:
    name = os.environ.get("WANYOU_SELENIUM_BROWSER", getattr(config, "SELENIUM_BROWSER", "edge"))
    name = (name or "edge").strip().lower()
    if name not in SUPPORTED_BROWSERS:
        raise ValueError(
            "Unsupported Selenium browser "
            f"{name!r}. Set WANYOU_SELENIUM_BROWSER to 'chrome' or 'edge'."
        )
    return name


def make_browser_options(browser_name: str, profile_dir: str, *, headless: bool = False):
    options = ChromeOptions() if browser_name == "chrome" else EdgeOptions()
    options.page_load_strategy = getattr(config, "PAGE_LOAD_STRATEGY", "eager")
    if headless:
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
    if browser_name == "edge":
        options.add_argument("--disable-features=msEdgeSidebarV2,EdgeWalletCheckout,msPdfAadIntegration")
    options.add_argument(f"--user-data-dir={profile_dir}")
    try:
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
    except Exception:
        pass
    return options


def make_webdriver(browser_name: str, options):
    if browser_name == "chrome":
        service = ChromeService(log_output=os.devnull)
        return webdriver.Chrome(options=options, service=service)
    service = EdgeService(log_output=os.devnull)
    return webdriver.Edge(options=options, service=service)
