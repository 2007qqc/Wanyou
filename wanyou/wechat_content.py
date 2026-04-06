import html
import os
import re
import time

import html2text
import requests

import config
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


def _llm_headers():
    api_key_env = (
        getattr(config, "WECHAT_IMAGE_LLM_API_KEY_ENV", "")
        or getattr(config, "LLM_API_KEY_ENV", "")
    )
    if not api_key_env:
        return None
    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        return None
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _extract_llm_content(data):
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = str(item.get("text", "")).strip()
                if text:
                    parts.append(text)
            elif isinstance(item, str):
                text = item.strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def classify_image_type_with_llm(image_url):
    if not getattr(config, "WECHAT_IMAGE_LLM_ENABLED", False):
        return "OTHER"

    headers = _llm_headers()
    if not headers:
        return "OTHER"

    base_url = (getattr(config, "WECHAT_IMAGE_LLM_BASE_URL", "") or config.LLM_BASE_URL).rstrip("/")
    model = getattr(config, "WECHAT_IMAGE_LLM_MODEL", "") or config.LLM_MODEL
    endpoint = f"{base_url}/chat/completions"
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": 8,
        "messages": [
            {
                "role": "system",
                "content": "你是图片分类器。只输出 TABLE、QRCODE 或 OTHER。",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "判断该图片是否为表格或二维码。"
                            "若是表格输出 TABLE，若包含二维码输出 QRCODE，否则输出 OTHER。"
                            "只能输出一个词。"
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            },
        ],
    }
    print(f"正在分类图片：{image_url}, LLM 请求头配置 {'已设置' if headers else '未设置'}")

    try:
        resp = requests.post(
            endpoint,
            headers=headers,
            json=body,
            timeout=getattr(config, "WECHAT_IMAGE_LLM_TIMEOUT_SECONDS", config.LLM_TIMEOUT_SECONDS),
        )
        resp.raise_for_status()
        text = _extract_llm_content(resp.json()).upper()
    except Exception:
        return "OTHER"
    print(f"正在分类图片：{image_url}, LLM 请求头配置 {'已设置' if headers else '未设置'}, 响应文本：{text}")

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


def enrich_items_with_content(session, items, timeout, sleep_seconds):
    for idx, item in enumerate(items, start=1):
        url = item.get("url")
        if not url:
            continue
        try:
            item.update(fetch_article_detail(session, url, timeout, sleep_seconds))
        except Exception as exc:
            item["content_error"] = str(exc)
        if sleep_seconds:
            time.sleep(sleep_seconds)
        if idx % 10 == 0:
            print(f"已抓取正文 {idx}/{len(items)}")
