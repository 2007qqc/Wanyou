import os
import re
from urllib.parse import urljoin

import requests
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

import config
from wanyou.utils_issue_filter import load_previous_titles, seen_in_previous_issue
from wanyou.utils_web import make_browser


def crawl_hall(doc, filename_jpg, base_images_dir):
    result = []
    browser = make_browser()
    try:
        for page_url in config.URL_HALL_PAGES:
            browser.get(page_url)
            events = browser.find_elements(By.CSS_SELECTOR, "div.timemain_a")
            for event in events:
                try:
                    day_element = event.find_element(By.CSS_SELECTOR, "b.size_40")
                    day = day_element.text.strip()
                    year_month = browser.execute_script("var node = arguments[0].nextSibling; while (node) { if (node.nodeType === Node.TEXT_NODE && node.textContent.trim() !== '') { return node.textContent.trim(); } node = node.nextSibling; } return '';", day_element)
                    time_text = event.find_element(By.CSS_SELECTOR, "b.size_bg").text.strip()
                    full_date = f"{year_month}-{day} {time_text}"
                except NoSuchElementException:
                    full_date = "N/A"
                try:
                    title = event.find_element(By.CSS_SELECTOR, "h3.yahei a").text.strip()
                except NoSuchElementException:
                    title = "N/A"
                try:
                    location = event.find_element(By.CSS_SELECTOR, "li.add").text.strip().replace("<br>", "")
                except NoSuchElementException:
                    location = "N/A"
                try:
                    price = event.find_element(By.CLASS_NAME, "money").text.strip().replace("<br>", "")
                except NoSuchElementException:
                    price = "N/A"
                img = event.find_element(By.TAG_NAME, "img")
                absolute_src = urljoin(browser.current_url, img.get_attribute("src"))
                result.append({"date": full_date, "title": title, "location": location, "price": price, "absolute_src": absolute_src})
    finally:
        browser.quit()

    result_refined = []
    titles = []
    previous_titles = load_previous_titles()
    for i, item in enumerate(result[::-1]):
        if item["title"] in titles or item["title"] in config.HALL_NO_CONSIDER:
            for item_refined in result_refined:
                if item_refined["title"] == item["title"]:
                    item_refined["date"].append(item["date"])
            continue
        if seen_in_previous_issue(item["title"], previous_titles):
            continue
        response = requests.get(item["absolute_src"], headers={"user-agent": config.USER_AGENT})
        poster_dir = os.path.join(base_images_dir, filename_jpg)
        os.makedirs(poster_dir, exist_ok=True)
        path = os.path.join(poster_dir, f"{i}.jpg")
        with open(path, "wb") as f:
            for chunk in response.iter_content(chunk_size=128):
                f.write(chunk)
        titles.append(item["title"])
        result_refined.append({"date": [item["date"]], "title": item["title"], "location": item["location"], "price": item["price"], "path": path})

    doc.write("# 新清华学堂\n\n")
    markdown_dir = os.path.dirname(getattr(doc, "name", "")) or os.getcwd()
    for item in result_refined:
        image_path = os.path.relpath(item["path"], start=markdown_dir).replace("\\", "/")
        doc.write(f"## {item['title']}\n\n")
        if len(item["date"]) == 1:
            doc.write(f"日期: {item['date'][0]}\n\n")
        else:
            doc.write("日期:\n\n")
            for date in item["date"]:
                doc.write(f"{date}\n\n")
        doc.write(f"地点: {item['location']}\n\n")
        doc.write(f"票价:\n{re.sub('\\n', '\\n\\n', item['price'])}\n\n")
        doc.write(f"![]({image_path})\n\n")
