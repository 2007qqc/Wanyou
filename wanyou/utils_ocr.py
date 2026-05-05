import base64
import mimetypes
import os
import re

import requests

import config
from wanyou.utils_llm import multimodal_complete


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


def _vision_ocr_mode():
    mode = str(getattr(config, "OCR_VISION_LLM_MODE", "fallback") or "fallback").strip().lower()
    if mode not in {"fallback", "prefer", "only"}:
        return "fallback"
    return mode


def _image_file_to_data_url(image_path):
    mime_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    try:
        with open(image_path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("ascii")
    except Exception:
        return ""
    return f"data:{mime_type};base64,{encoded}"


def ocr_image_with_llm(image_ref):
    if not getattr(config, "OCR_VISION_LLM_ENABLED", False):
        return ""

    image_input = str(image_ref or "").strip()
    if not image_input:
        return ""
    if os.path.isfile(image_input):
        image_input = _image_file_to_data_url(image_input)
    if not image_input:
        return ""

    provider = getattr(config, "OCR_VISION_LLM_PROVIDER", "") or getattr(config, "IMAGE_LLM_PROVIDER", "")
    model = getattr(config, "OCR_VISION_LLM_MODEL", "") or getattr(config, "IMAGE_LLM_MODEL", "")
    api_key_env = getattr(config, "OCR_VISION_LLM_API_KEY_ENV", "") or getattr(config, "IMAGE_LLM_API_KEY_ENV", "")
    base_url = getattr(config, "OCR_VISION_LLM_BASE_URL", "") or getattr(config, "IMAGE_LLM_BASE_URL", "")
    if not provider or not model or not api_key_env:
        return ""

    text = multimodal_complete(
        "你是严谨的图片文字识别助手。",
        (
            "请识别图片中的中文和英文文字。"
            "保留通知中的标题、时间、地点、报名方式、链接、联系人等信息。"
            "如果图片包含表格，请尽量输出为有效 Markdown 表格。"
            "不要编造图片中不存在的信息；如果没有可识别文字，输出空字符串。"
            "只输出识别出的正文。"
        ),
        image_input,
        provider=provider,
        model=model,
        api_key_env=api_key_env,
        base_url=base_url or None,
        timeout_seconds=getattr(config, "OCR_VISION_LLM_TIMEOUT_SECONDS", 20),
        max_tokens=1200,
        temperature=0,
    )
    return (text or "").strip()


def ocr_space_file(image_path):
    if not getattr(config, "MYHOME_IMAGE_OCR_ENABLED", False):
        return ""
    if not os.path.isfile(image_path):
        return ""

    mode = _vision_ocr_mode()
    if mode in {"prefer", "only"}:
        llm_text = ocr_image_with_llm(image_path)
        if llm_text or mode == "only":
            return llm_text

    ocr_text = ""
    api_key = _ocr_space_api_key()
    endpoint = getattr(
        config,
        "MYHOME_IMAGE_OCR_SPACE_URL",
        getattr(config, "WECHAT_OCR_SPACE_URL", "https://api.ocr.space/parse/image"),
    ).strip()
    if api_key and endpoint:
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
            ocr_text = _parse_ocr_space_text(resp.json())
        except Exception:
            ocr_text = ""

    if not ocr_text and mode == "fallback":
        return ocr_image_with_llm(image_path)
    return ocr_text


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
