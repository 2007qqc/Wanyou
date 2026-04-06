import os
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import config
from wanyou.utils_dates import days_since_date
from wanyou.utils_web import make_browser, build_requests_session, open_in_new_tab
from wanyou.utils_html import html_to_markdown, save_content
from wanyou.utils_ocr import convert_markdown_images_to_text
from wanyou.decider import should_copy_with_llm


def crawl_myhome(doc, base_images_dir, username, password):
    browser = make_browser()
    browser.get(config.URL_MYHOME)
    button = browser.find_element(By.ID, 'i_user')
    button.send_keys(username)
    button = browser.find_element(By.ID, 'i_pass')
    button.send_keys(password)
    button = browser.find_element(By.CSS_SELECTOR, 'a.btn.btn-lg.btn-primary.btn-block')
    button.click()
    time.sleep(config.SLEEP_SECONDS)

    browser.get(config.URL_MYHOME)
    session = build_requests_session(browser)

    notice_blocks = browser.find_elements(By.XPATH,
        "//a[contains(@href, 'News_notice_Detail.aspx') and @target='_blank']")
    seen_urls = set()
    web = browser.window_handles[0]
    time.sleep(1)

    titles = []
    full_texts = []
    image_counter = [0]
    inline_images_dir = os.path.join(base_images_dir, "inline")

    for block in notice_blocks:
        try:
            url = block.get_attribute('href')
            time.sleep(1)

            if url not in seen_urls:
                seen_urls, browser = open_in_new_tab(url, seen_urls, browser, web)

                time_label = browser.find_element(By.ID, "News_notice_DetailCtrl1_lbladd_time")
                date = time_label.text
                date = date[-17:-13]+"-"+date[-12:-10]+"-"+date[-9:-7]

                if days_since_date(date) > config.DAYS_WINDOW_MYHOME:
                    break

                title = browser.find_element(By.ID, "News_notice_DetailCtrl1_lblTitle").text
                if all((not(sub in title)) for sub in config.MYHOME_NO_CONSIDER):
                    decision = should_copy_with_llm("myhome", title, date)
                    if decision is None:
                        decision = input('是否拷贝"'+title+'"的信息 (y/n, default y)\n') != "n"
                    if decision:
                        container = WebDriverWait(browser, config.WAIT_TIMEOUT).until(
                            EC.presence_of_element_located((By.XPATH,
                            "//td[@class='content1 content2' and @colspan='2' and contains(@style, 'text-align: left')]")))
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

        except Exception as e:
            print(f"处理区块时出错：{str(e)}")

    browser.quit()
    doc.write("# 家园网信息\n\n")
    save_content(titles, full_texts, doc)
