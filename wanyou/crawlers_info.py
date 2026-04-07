import os
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException

import config
from wanyou.utils_dates import days_since_date
from wanyou.utils_web import make_browser, build_requests_session, open_in_new_tab
from wanyou.utils_html import html_to_markdown, save_content
from wanyou.decider import resolve_copy_decision


def crawl_info(doc, base_images_dir, username, password):
    browser = make_browser()
    browser.get(config.URL_INFO)
    button = browser.find_element(By.ID, 'i_user')
    button.send_keys(username)
    button = browser.find_element(By.ID, 'i_pass')
    button.send_keys(password)
    button = browser.find_element(By.CSS_SELECTOR, 'a.btn.btn-lg.btn-primary.btn-block')
    button.click()
    time.sleep(config.SLEEP_SECONDS)

    browser.get(config.URL_INFO)
    session = build_requests_session(browser)

    button = browser.find_element(By.ID, 'LM_JWGG')
    button.click()

    notice_blocks = browser.find_elements(By.CSS_SELECTOR, 'div.you')
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
            link = block.find_element(By.CSS_SELECTOR, 'div.title > a')
            url = link.get_attribute('href')

            if url not in seen_urls:
                seen_urls, browser = open_in_new_tab(url, seen_urls, browser, web)

                time.sleep(2)
                time_label = browser.find_element(By.ID, "timeFlag")
                time_span = time_label.find_element(By.TAG_NAME, "span")
                date = time_span.text[:10]

                if (days_since_date(date) > config.DAYS_WINDOW_INFO) & up:
                    break

                title = browser.find_element(By.CLASS_NAME, "title").text
                decision = resolve_copy_decision("info", title, date)
                if decision:
                    container = WebDriverWait(browser, config.WAIT_TIMEOUT).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "xiangqingchakan")))
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

    browser.quit()
    doc.write("# 教务通知\n\n")
    save_content(titles, full_texts, doc)
