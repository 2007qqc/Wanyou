import os
import re
import requests
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from urllib.parse import urljoin

import config
from wanyou.utils_dates import days_since_date
from wanyou.utils_web import make_browser


def crawl_hall(doc, filename_jpg, base_images_dir):
    URL_MYHOMEs = config.URL_HALL_PAGES

    result = []
    browser = make_browser()

    try:
        for URL_MYHOME in URL_MYHOMEs:
            browser.get(URL_MYHOME)

            events = browser.find_elements(By.CSS_SELECTOR, 'div.timemain_a')

            for event in events:
                try:
                    day_element = event.find_element(By.CSS_SELECTOR, 'b.size_40')
                    day = day_element.text.strip()

                    year_month_script = """
                    var node = arguments[0].nextSibling;
                    while (node) {
                        if (node.nodeType === Node.TEXT_NODE && node.textContent.trim() !== '') {
                            return node.textContent.trim();
                        }
                        node = node.nextSibling;
                    }
                    return '';
                    """
                    year_month = browser.execute_script(year_month_script, day_element)

                    time_element = event.find_element(By.CSS_SELECTOR, 'b.size_bg')
                    time = time_element.text.strip()

                    full_date = f"{year_month}-{day} {time}"
                except NoSuchElementException:
                    full_date = "N/A"

                try:
                    title_element = event.find_element(By.CSS_SELECTOR, 'h3.yahei a')
                    title = title_element.text.strip()
                except NoSuchElementException:
                    title = "N/A"

                try:
                    location_element = event.find_element(By.CSS_SELECTOR, 'li.add')
                    location = location_element.text.strip().replace('<br>', '')
                except NoSuchElementException:
                    location = "N/A"

                try:
                    price_element = event.find_element(By.CLASS_NAME, 'money')
                    price = price_element.text.strip().replace('<br>', '')
                except NoSuchElementException:
                    price = "N/A"

                img = event.find_element(By.TAG_NAME, 'img')
                relative_src = img.get_attribute('src')
                absolute_src = urljoin(browser.current_url, relative_src)

                result.append({
                    "date": full_date,
                    "title": title,
                    "location": location,
                    "price": price,
                    "absolute_src": absolute_src
                })
    finally:
        browser.quit()

    result_refined = []
    titles = []

    for i, item in enumerate(result[::-1]):
        date = (item["date"])[:10]
        if (item["title"] not in titles) & (item["title"] not in config.HALL_NO_CONSIDER) & (-config.HALL_RECENT_DAYS < days_since_date(date) < 0):
            headers={
                'user-agent': config.USER_AGENT}
            re1=requests.get(item["absolute_src"], headers=headers)
            poster_dir = os.path.join(base_images_dir, filename_jpg)
            os.makedirs(poster_dir, exist_ok=True)
            path = os.path.join(poster_dir, str(i) + ".jpg")
            with open(path, 'wb') as f:
                for chunk in re1.iter_content(chunk_size=128):
                    f.write(chunk)

            titles.append(item["title"])
            result_refined.append({
            "date": [item["date"],],
            "title": item["title"],
            "location": item["location"],
            "price": item["price"],
            "path": path
            })

        else:
            for item_refined in result_refined:
                if item_refined["title"] == item["title"]:
                    item_refined["date"].append(item["date"])

    doc.write("# 新清华学堂\n\n")
    markdown_dir = os.path.dirname(getattr(doc, "name", "")) or os.getcwd()

    for item in result_refined:
        image_path = os.path.relpath(item["path"], start=markdown_dir).replace("\\", "/")
        doc.write(f"## {item['title']}\n\n")
        if len(item['date']) == 1:
            doc.write(f"日期: {(item['date'])[0]}\n\n")
        else:
            doc.write(f"日期: \n\n")
            for date in item['date']:
                doc.write(f"{date}\n\n")
        doc.write(f"地点: {item['location']}\n\n")
        doc.write('票价: \n{}\n\n'.format(re.sub('\n', '\n\n', item['price'])))
        doc.write(f"![]({image_path})\n\n")
