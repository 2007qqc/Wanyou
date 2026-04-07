import os
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import config
from wanyou.utils_dates import days_since_date, is_after_next_monday
from wanyou.utils_web import make_browser, build_requests_session
from wanyou.utils_html import html_to_markdown, save_content
from wanyou.decider import resolve_copy_decision


def extract_content(text):
    markers = [m.start() for m in re.finditer(r"第\d+讲：", text)]
    start_index = markers[0]
    end_match = re.search(r"3－教师", text[start_index:])
    if not end_match:
        return "「第X讲：」后无「3－教师」"
    end_index = start_index + end_match.end()
    return text[start_index:end_index]


def crawl_lib(doc, base_images_dir):
    browser = make_browser()
    browser.get(config.URL_LIB_NOTICE)
    session = build_requests_session(browser)

    titles = []
    full_texts = []
    image_counter = [0]
    inline_images_dir = os.path.join(base_images_dir, "inline")
    idx = 0
    while True:
        notice_labels = browser.find_elements(By.CSS_SELECTOR, 'div.notice-label.color1')
        notice_blocks = browser.find_elements(By.CLASS_NAME, "notice-list-tt")
        if idx >= len(notice_labels) or idx >= len(notice_blocks):
            break
        label = notice_labels[idx]
        block = notice_blocks[idx]
        idx += 1
        try:
            if label.text != "开馆通知":
                continue
            title = block.text
            notice_link = block.find_element(By.TAG_NAME, "a")
            notice_link.click()

            class_info = browser.find_element(By.CLASS_NAME, "info")
            time_label = class_info.find_element(By.CLASS_NAME, "date")
            date = time_label.text
            date = date[-11:-7]+"-"+date[-6:-4]+"-"+date[-3:-1]

            if days_since_date(date) > config.DAYS_WINDOW_LIB:
                browser.back()
                continue

            if all((not(sub in title)) for sub in config.LIB_NO_CONSIDER):
                decision = resolve_copy_decision("lib_notice", title, date)
                if decision:
                    container = WebDriverWait(browser, config.WAIT_TIMEOUT).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "concon")))
                    titles.append(title)
                    full_texts.append(
                        html_to_markdown(
                            container,
                            browser.current_url,
                            session,
                            inline_images_dir,
                            image_counter,
                            "lib",
                            browser.current_url,
                        )
                    )

            browser.back()

        except Exception as e:
            print(f"处理区块时出错：{str(e)}")

    browser.quit()

    browser = make_browser()
    browser.get(config.URL_LIB_EVENT)

    seen_urls = set()
    iddate = 0
    idx = 0
    while True:
        boxes = browser.find_elements(By.CLASS_NAME, "rl-list")
        if idx >= len(boxes):
            break
        box = boxes[idx]

        notice_blocks = box.find_elements(By.CSS_SELECTOR, 'div.rl-title.txt-elise')
        year = box.find_element(
            By.XPATH, "//div[@class='rl-year' and string-length(text())=4]"
        ).text

        if iddate >= len(notice_blocks):
            idx += 1
            iddate = 0
            continue

        block = notice_blocks[iddate]
        iddate += 1

        try:
            url = block.get_attribute('href')

            if url not in seen_urls:
                title = block.text
                block.click()

                if 'lib.tsinghua.edu.cn' not in browser.current_url:
                    browser.back()
                    continue

                try:
                    time_label = WebDriverWait(browser, config.WAIT_TIMEOUT).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "infoBarsList-value"))
                    )
                    date = time_label.text
                except Exception:
                    time_label = WebDriverWait(browser, config.WAIT_TIMEOUT).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".infoBarsList .infoBarsList-value"))
                    )
                    date = time_label.text
                date = year+"-"+date.split("月")[0]+"-"+date.split("月")[1].split("日")[0]

                if not is_after_next_monday(date):
                    browser.back()
                    continue

                decision = resolve_copy_decision("lib_event", title, date)
                if decision:
                    container = WebDriverWait(browser, config.WAIT_TIMEOUT).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.material-value.editor-width")))
                    titles.append(title)
                    if any((sub in title) for sub in config.LIB_CONSIDER):
                        full_texts.append(
                            extract_content(
                                html_to_markdown(
                                    container,
                                    browser.current_url,
                                    session,
                                    inline_images_dir,
                                    image_counter,
                                    "lib",
                                    browser.current_url,
                                )
                            )
                        )
                    else:
                        full_texts.append(
                            html_to_markdown(
                                container,
                                browser.current_url,
                                session,
                                inline_images_dir,
                                image_counter,
                                "lib",
                                browser.current_url,
                            )
                        )

                browser.back()

        except Exception as e:
            print(f"处理区块时出错：{str(e)}")

    browser.quit()
    doc.write("# 图书馆信息\n\n")
    save_content(titles, full_texts, doc)
