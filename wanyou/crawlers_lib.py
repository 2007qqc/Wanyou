import os
import re

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import config
from wanyou.decider import resolve_copy_decision
from wanyou.utils_html import html_to_markdown, save_content
from wanyou.utils_issue_filter import load_previous_titles, seen_in_previous_issue
from wanyou.utils_web import build_requests_session, make_browser


def extract_content(text: str) -> str:
    markers = [m.start() for m in re.finditer(r"第\d+讲：", text)]
    if not markers:
        return text
    start_index = markers[0]
    end_match = re.search(r"教师|主讲人", text[start_index:])
    if not end_match:
        return text[start_index:]
    end_index = start_index + end_match.start()
    return text[start_index:end_index].strip()


def _extract_box_year(box) -> str:
    selectors = [(By.CSS_SELECTOR, ".rl-year"), (By.XPATH, ".//*[contains(@class, 'rl-year')]")]
    for by, value in selectors:
        try:
            nodes = box.find_elements(by, value)
        except Exception:
            continue
        for node in nodes:
            match = re.search(r"20\d{2}", (node.text or "").strip())
            if match:
                return match.group(0)
    match = re.search(r"20\d{2}", box.text or "")
    return match.group(0) if match else ""


def crawl_lib(doc, base_images_dir):
    previous_titles = load_previous_titles()
    browser = make_browser()
    browser.get(config.URL_LIB_NOTICE)
    session = build_requests_session(browser)
    titles = []
    full_texts = []
    image_counter = [0]
    inline_images_dir = os.path.join(base_images_dir, "inline")
    idx = 0
    while True:
        notice_labels = browser.find_elements(By.CSS_SELECTOR, "div.notice-label.color1")
        notice_blocks = browser.find_elements(By.CLASS_NAME, "notice-list-tt")
        if idx >= len(notice_labels) or idx >= len(notice_blocks):
            break
        label = notice_labels[idx]
        block = notice_blocks[idx]
        idx += 1
        try:
            if label.text != "开馆通知":
                continue
            title = block.text.strip()
            notice_link = block.find_element(By.TAG_NAME, "a")
            notice_link.click()
            class_info = browser.find_element(By.CLASS_NAME, "info")
            time_label = class_info.find_element(By.CLASS_NAME, "date")
            date = time_label.text
            date = f"{date[-11:-7]}-{date[-6:-4]}-{date[-3:-1]}"
            if seen_in_previous_issue(title, previous_titles):
                browser.back(); continue
            if all(sub not in title for sub in config.LIB_NO_CONSIDER):
                if resolve_copy_decision("lib_notice", title, date):
                    container = WebDriverWait(browser, config.WAIT_TIMEOUT).until(EC.presence_of_element_located((By.CLASS_NAME, "concon")))
                    titles.append(title)
                    full_texts.append(html_to_markdown(container, browser.current_url, session, inline_images_dir, image_counter, "lib", browser.current_url))
            browser.back()
        except Exception:
            continue
    browser.quit()

    browser = make_browser()
    browser.get(config.URL_LIB_EVENT)
    session = build_requests_session(browser)
    seen_urls = set()
    block_index = 0
    item_index = 0
    while True:
        boxes = browser.find_elements(By.CLASS_NAME, "rl-list")
        if block_index >= len(boxes):
            break
        box = boxes[block_index]
        notice_blocks = box.find_elements(By.CSS_SELECTOR, "div.rl-title.txt-elise")
        year = _extract_box_year(box)
        if item_index >= len(notice_blocks):
            block_index += 1
            item_index = 0
            continue
        block = notice_blocks[item_index]
        item_index += 1
        try:
            url = block.get_attribute("href")
            if not url or url in seen_urls:
                continue
            title = block.text.strip()
            block.click()
            if "lib.tsinghua.edu.cn" not in browser.current_url:
                browser.back(); continue
            try:
                time_label = WebDriverWait(browser, config.WAIT_TIMEOUT).until(EC.presence_of_element_located((By.CLASS_NAME, "infoBarsList-value")))
                date = time_label.text
            except Exception:
                time_label = WebDriverWait(browser, config.WAIT_TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".infoBarsList .infoBarsList-value")))
                date = time_label.text
            month_day = re.findall(r"(\d{1,2})", date)
            if len(month_day) >= 2 and year:
                month, day = month_day[:2]
                date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            if seen_in_previous_issue(title, previous_titles):
                browser.back(); continue
            if resolve_copy_decision("lib_event", title, date):
                container = WebDriverWait(browser, config.WAIT_TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.material-value.editor-width")))
                titles.append(title)
                markdown_text = html_to_markdown(container, browser.current_url, session, inline_images_dir, image_counter, "lib", browser.current_url)
                full_texts.append(extract_content(markdown_text) if any(sub in title for sub in config.LIB_CONSIDER) else markdown_text)
            browser.back()
        except Exception:
            continue
    browser.quit()
    doc.write("# 图书馆信息\n\n")
    save_content(titles, full_texts, doc)
