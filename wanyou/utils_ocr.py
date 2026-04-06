import os
import re

import requests

import config


def _ocr_space_api_key():
    env_name = getattr(config, "MYHOME_IMAGE_OCR_API_KEY_ENV", "OCR_SPACE_API_KEY")
    return os.environ.get(env_name, "").strip()


def _parse_ocr_space_text(payload):
    if not isinstance(payload, dict):
        return ""
    if payload.get("IsErroredOnProcessing"):
        return ""
    parsed_results = payload.get("ParsedResults")
    if not isinstance(parsed_results, list):
        return ""

    lines = []
    for result in parsed_results:
        if not isinstance(result, dict):
            continue
        text = str(result.get("ParsedText", "")).strip()
        if text:
            lines.append(text)
    return "\n".join(lines).strip()


def ocr_space_file(image_path):
    if not getattr(config, "MYHOME_IMAGE_OCR_ENABLED", False):
        return ""
    if not os.path.isfile(image_path):
        return ""

    api_key = _ocr_space_api_key()
    if not api_key:
        return ""

    endpoint = getattr(
        config,
        "MYHOME_IMAGE_OCR_SPACE_URL",
        getattr(config, "WECHAT_OCR_SPACE_URL", "https://api.ocr.space/parse/image"),
    ).strip()
    if not endpoint:
        return ""
    endpoint = endpoint.replace("/parse/imageurl", "/parse/image")

    timeout = getattr(config, "MYHOME_IMAGE_OCR_TIMEOUT_SECONDS", 30)
    language = getattr(config, "MYHOME_IMAGE_OCR_LANGUAGE", "chs")
    engine = getattr(config, "MYHOME_IMAGE_OCR_ENGINE", 1)

    try:
        filename = os.path.basename(image_path) or "image.jpg"
        data = {
            "apikey": api_key,
            "language": str(language),
            "OCREngine": str(engine),
        }
        with open(image_path, "rb") as image_file:
            files = {"file": (filename, image_file)}
            resp = requests.post(endpoint, data=data, files=files, timeout=timeout)
        resp.raise_for_status()
        return _parse_ocr_space_text(resp.json())
    except Exception:
        return ""


def _extract_image_path(markdown_target):
    target = markdown_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if '"' in target:
        target = target.split('"', 1)[0].strip()
    return target


def convert_markdown_images_to_text(markdown_text):
    if not markdown_text:
        return markdown_text

    keep_image = getattr(config, "MYHOME_IMAGE_OCR_KEEP_IMAGE", False)
    cache = {}

    def _replace(match):
        whole = match.group(0)
        image_target = match.group(1)
        image_path = _extract_image_path(image_target)

        if image_path not in cache:
            cache[image_path] = ocr_space_file(image_path)
        ocr_text = cache[image_path]

        if not ocr_text:
            return whole

        if keep_image:
            return f"{whole}\n\n[图片文字]\n{ocr_text}\n"
        return f"\n\n[图片文字]\n{ocr_text}\n\n"

    # Markdown image pattern: ![alt](path "title")
    return re.sub(r"!\[[^\]]*\]\(([^)]+)\)", _replace, markdown_text)
