import concurrent.futures
import html
import os
import re
import time

import html2text
import requests
import config
from wanyou.utils_llm import multimodal_complete
from wanyou.wechat_client import fetch_article_html, normalize_url


def extract_js_content(html_text):
    match = re.search(r'<div[^>]+id="js_content"[^>]*>(.*?)</div>', html_text, re.S)
    if match:
        return match.group(1)

    match = re.search(r"<body[^>]*>(.*?)</body>", html_text, re.S | re.I)
    if match:
        return match.group(1)
    return html_text


def extract_publish_time(html_text):
    match = re.search(r'id="publish_time"[^>]*>(.*?)</', html_text, re.S)
    if match:
        return html.unescape(match.group(1)).strip()
    match = re.search(r'publish_time\s*=\s*"(.*?)"', html_text)
    if match:
        return match.group(1).strip()
    return ""


def extract_author(html_text):
    match = re.search(r'id="js_author_name"[^>]*>(.*?)</', html_text, re.S)
    if match:
        return html.unescape(match.group(1)).strip()
    match = re.search(r'var\s+author\s*=\s*"(.*?)"', html_text)
    if match:
        return match.group(1).strip()
    return ""


def extract_content_url_from_img_tag(img_tag):
    for attr in ("data-src", "src"):
        match = re.search(rf'{attr}\s*=\s*(["\'])(.*?)\1', img_tag, re.I | re.S)
        if match:
            return normalize_url(match.group(2).strip())
        match = re.search(rf"{attr}\s*=\s*([^\s>]+)", img_tag, re.I)
        if match:
            return normalize_url(match.group(1).strip('"\''))
    return None


def replace_images_with_placeholders(content_html):
    image_urls = []

    def _replace(match):
        img_tag = match.group(0)
        img_url = extract_content_url_from_img_tag(img_tag)
        if not img_url:
            return ""
        image_urls.append(img_url)
        index = len(image_urls)
        return f"<p>[[IMG_OCR_{index}]]</p>"

    replaced = re.sub(r"<img\b[^>]*>", _replace, content_html, flags=re.I)
    return replaced, image_urls


def extract_ocr_text_from_response(data):
    if not isinstance(data, dict):
        return ""
    if data.get("IsErroredOnProcessing"):
        return ""
    parsed_results = data.get("ParsedResults")
    if not isinstance(parsed_results, list):
        return ""
    lines = []
    for result in parsed_results:
        if not isinstance(result, dict):
            continue
        text = str(result.get("ParsedText", "")).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _to_bool_str(value):
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "false"):
            return text
    return "true" if bool(value) else "false"


def classify_image_type_with_llm(image_url):
    if not getattr(config, "WECHAT_IMAGE_LLM_ENABLED", False):
        return "OTHER"

    provider = getattr(config, "WECHAT_IMAGE_LLM_PROVIDER", "") or getattr(config, "LLM_PROVIDER", "")
    model = getattr(config, "WECHAT_IMAGE_LLM_MODEL", "") or getattr(config, "LLM_MODEL", "")
    api_key_env = getattr(config, "WECHAT_IMAGE_LLM_API_KEY_ENV", "") or getattr(config, "LLM_API_KEY_ENV", "")
    base_url = getattr(config, "WECHAT_IMAGE_LLM_BASE_URL", "") or getattr(config, "LLM_BASE_URL", "")

    text = multimodal_complete(
        "你是图片分类器。只输出 TABLE、QRCODE 或 OTHER。",
        (
            "判断该图片是否为表格或二维码。"
            "若是表格输出 TABLE，若包含二维码输出 QRCODE，否则输出 OTHER。"
            "只能输出一个词。"
        ),
        image_url,
        provider=provider,
        model=model,
        api_key_env=api_key_env or None,
        base_url=base_url or None,
        timeout_seconds=getattr(config, "WECHAT_IMAGE_LLM_TIMEOUT_SECONDS", config.LLM_TIMEOUT_SECONDS),
        max_tokens=8,
        temperature=0,
    )
    text = (text or "").upper()
    if text.startswith("TABLE"):
        return "TABLE"
    if text.startswith("QRCODE"):
        return "QRCODE"
    return "OTHER"


def call_ocr_space(image_url):
    if not getattr(config, "WECHAT_OCR_ENABLED", True):
        return ""

    key_env = getattr(config, "WECHAT_OCR_SPACE_API_KEY_ENV", "OCR_SPACE_API_KEY")
    api_key = os.environ.get(key_env, "").strip()
    if not api_key:
        return ""

    endpoint = getattr(config, "WECHAT_OCR_SPACE_URL", "https://api.ocr.space/parse/imageurl").strip()
    if not endpoint:
        return ""

    params = {
        "apikey": api_key,
        "url": image_url,
        "language": str(getattr(config, "WECHAT_OCR_SPACE_LANGUAGE", "chs")),
        "isOverlayRequired": _to_bool_str(
            getattr(config, "WECHAT_OCR_SPACE_IS_OVERLAY_REQUIRED", False)
        ),
        "detectOrientation": _to_bool_str(
            getattr(config, "WECHAT_OCR_SPACE_DETECT_ORIENTATION", False)
        ),
        "isTable": _to_bool_str(getattr(config, "WECHAT_OCR_SPACE_IS_TABLE", False)),
        "OCREngine": str(getattr(config, "WECHAT_OCR_SPACE_ENGINE", 1)),
    }

    try:
        resp = requests.get(
            endpoint,
            params=params,
            timeout=getattr(config, "WECHAT_OCR_TIMEOUT_SECONDS", 30),
        )
        resp.raise_for_status()
        payload = resp.json()
        return extract_ocr_text_from_response(payload)
    except Exception:
        return ""


def fetch_image_ocr_texts(session, image_urls, timeout, sleep_seconds):
    _ = session, timeout
    max_images = getattr(config, "WECHAT_OCR_MAX_IMAGES_PER_ARTICLE", 0)
    texts = []
    types = []
    for index, image_url in enumerate(image_urls, start=1):
        if max_images and index > max_images:
            texts.append("")
            types.append("OTHER")
            continue
        try:
            image_type = classify_image_type_with_llm(image_url)
            types.append(image_type)
            if image_type in ("TABLE", "QRCODE"):
                texts.append("")
            else:
                texts.append(call_ocr_space(image_url))
        except Exception:
            texts.append("")
            types.append("OTHER")
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return texts, types


def inject_ocr_text_into_markdown(content_md, image_urls, image_ocr_texts, image_types):
    def _replace(match):
        index = int(match.group(1))
        image_url = ""
        image_type = "OTHER"
        text = ""
        if 0 < index <= len(image_urls):
            image_url = image_urls[index - 1] or ""
        if 0 < index <= len(image_types):
            image_type = image_types[index - 1] or "OTHER"
        if 0 < index <= len(image_ocr_texts):
            text = (image_ocr_texts[index - 1] or "").strip()
        if image_type in ("TABLE", "QRCODE") and image_url:
            return f"![图片{index}]({image_url})"
        if text:
            return f"[图片文字 {index}] {text}"
        return ""

    rendered = re.sub(r"\[\[IMG_OCR_(\d+)\]\]", _replace, content_md)
    rendered = re.sub(r"\n{3,}", "\n\n", rendered).strip()
    return rendered


def fetch_article_detail(session, url, timeout, sleep_seconds):
    detail = {
        "content": "",
        "content_format": "md",
        "image_urls": [],
        "image_ocr_texts": [],
        "image_llm_types": [],
    }

    html_text = fetch_article_html(session, url, timeout)
    content_html = extract_js_content(html_text)
    if content_html:
        if getattr(config, "RAW_COLLECTION_MODE", False):
            content_html = re.sub(r"<img\b[^>]*>", "", content_html, flags=re.I)
            detail["content"] = html2text.html2text(content_html).strip()
        else:
            content_html_with_markers, image_urls = replace_images_with_placeholders(content_html)
            content_md = html2text.html2text(content_html_with_markers).strip()
            image_ocr_texts, image_llm_types = fetch_image_ocr_texts(
                session, image_urls, timeout, sleep_seconds
            )
            detail["content"] = inject_ocr_text_into_markdown(
                content_md, image_urls, image_ocr_texts, image_llm_types
            )
            detail["image_urls"] = image_urls
            detail["image_ocr_texts"] = image_ocr_texts
            detail["image_llm_types"] = image_llm_types

    detail["publish_time"] = extract_publish_time(html_text)
    detail["author"] = extract_author(html_text)
    return detail


def _clone_session_with_auth(session):
    cloned = requests.Session()
    try:
        cloned.headers.update(session.headers)
    except Exception:
        pass
    return cloned


def _fetch_item_detail_job(index, total, item, timeout, sleep_seconds, auth_session):
    url = item.get("url")
    title = (item.get("title") or "无标题")[:40]
    account = item.get("account_keyword") or "未知公众号"
    if not url:
        return index, {}, f"公众号：跳过无链接推送 {index}/{total}：{account} - {title}"

    try:
        detail = fetch_article_detail(auth_session, url, timeout, sleep_seconds)
        return index, detail, f"公众号：正文下载完成 {index}/{total}：{account} - {title}"
    except Exception as exc:
        return index, {"content_error": str(exc)}, f"公众号：正文下载失败 {index}/{total}：{account} - {title}，{exc}"


def enrich_items_with_content(session, items, timeout, sleep_seconds):
    total = len(items)
    if total <= 0:
        return

    max_workers = max(1, int(getattr(config, "WECHAT_DOWNLOAD_MAX_WORKERS", 4) or 1))
    if max_workers == 1 or total == 1:
        for idx, item in enumerate(items, start=1):
            url = item.get("url")
            title = (item.get("title") or "无标题")[:40]
            account = item.get("account_keyword") or "未知公众号"
            if not url:
                print(f"公众号：跳过无链接推送 {idx}/{total}：{account} - {title}")
                continue
            try:
                print(f"公众号：正在下载正文 {idx}/{total}：{account} - {title}")
                item.update(fetch_article_detail(session, url, timeout, sleep_seconds))
            except Exception as exc:
                item["content_error"] = str(exc)
                print(f"公众号：正文下载失败 {idx}/{total}：{account} - {title}，{exc}")
            if sleep_seconds:
                time.sleep(sleep_seconds)
        return

    print(f"公众号：正在并行下载正文，共 {total} 条，最大并行数 {max_workers}")
    futures = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for idx, item in enumerate(items, start=1):
            title = (item.get("title") or "无标题")[:40]
            account = item.get("account_keyword") or "未知公众号"
            print(f"公众号：已加入下载队列 {idx}/{total}：{account} - {title}")
            worker_session = _clone_session_with_auth(session)
            future = executor.submit(
                _fetch_item_detail_job,
                idx,
                total,
                item,
                timeout,
                sleep_seconds,
                worker_session,
            )
            futures[future] = item

        for future in concurrent.futures.as_completed(futures):
            item = futures[future]
            try:
                idx, detail, message = future.result()
                _ = idx
            except Exception as exc:
                detail = {"content_error": str(exc)}
                message = f"公众号：正文下载线程异常，{exc}"
            item.update(detail)
            print(message)
