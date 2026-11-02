"""公众号正文里的报名二维码识别与落地。

微信读书 `/web/mp/content` 能拿到整篇正文和图片。这里在正文图片里筛出可能
包含二维码的图（图片前文含“二维码/扫码/问卷/报名/群”等），下载后用 OpenCV
检测/解码；识别出的二维码保存成本地文件，供成稿以图片形式附在卡片里。

没装 OpenCV 时不做识别（宁可没有图，也不要把普通配图当成二维码）。
"""

import hashlib
import os
import re

import requests

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover - 依赖缺失时停用二维码识别
    cv2 = None
    np = None

import config


QR_CONTEXT_RE = re.compile(r"二维码|扫码|扫描|问卷|报名|招募|加入|群聊|群二维码|表单")
_ALT_RULES = (
    ("wjx", "报名问卷二维码"),
    ("weixin.qq.com/f/", "报名群二维码"),
)
_EXT_BY_TYPE = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/70.0.3538.25 Safari/537.36"
)


def _image_dir():
    path = str(getattr(config, "WECHAT_QR_IMAGE_DIR", "output/wechat_qr") or "output/wechat_qr")
    os.makedirs(path, exist_ok=True)
    return path


def _download(url, timeout=15):
    headers = {"user-agent": _USER_AGENT, "referer": "https://weread.qq.com/"}
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "")
    except Exception:
        return b"", ""


def _to_cv_image(data):
    if cv2 is None or np is None:
        return None
    try:
        return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None


def _qr_like_image(image):
    """二维码图基本是黑白高对比；用来过滤“检测到定位点但解不出”的照片误报。"""
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        ratio = float(((gray < 80) | (gray > 180)).mean())
    except Exception:
        return False
    return ratio >= 0.85


def detect_qr(data):
    """返回 (is_qr, decoded_text)。解出内容或检测到二维码定位点都算二维码。"""
    image = _to_cv_image(data)
    if image is None or cv2 is None:
        return False, ""
    variants = [image, cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)]
    for scale in (2, 3):
        variants.append(cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC))
    detector = cv2.QRCodeDetector()
    curved = getattr(detector, "detectAndDecodeCurved", None)
    for variant in variants:
        try:
            text, _points, _ = detector.detectAndDecode(variant)
        except Exception:
            text = ""
        if text:
            return True, text
        if callable(curved):
            try:
                text, points, _ = curved(variant)
            except Exception:
                text, points = "", None
            if text:
                return True, text
            if points is not None and _qr_like_image(image):
                try:
                    if len(points):
                        return True, ""
                except TypeError:
                    return True, ""
        try:
            retval, infos, points, _ = detector.detectAndDecodeMulti(variant)
        except Exception:
            infos, points = (), None
        decoded = [info for info in (infos or ()) if info]
        if decoded:
            return True, decoded[0]
        if points is not None and _qr_like_image(image):
            try:
                if len(points):
                    return True, ""
            except TypeError:
                return True, ""
    return False, ""


def _alt_for(decoded, ctx):
    for marker, alt in _ALT_RULES:
        if marker in (decoded or "").lower():
            return alt
    if "问卷" in (ctx or ""):
        return "报名问卷二维码"
    if "群" in (ctx or ""):
        return "报名群二维码"
    return "报名二维码"


def collect_qr_images(item, *, max_images=None, max_candidates=None):
    """从 item['image_entries'] 里挑出二维码，保存到本地，返回 [{path, alt, decoded}]。"""
    entries = item.get("image_entries") or []
    if not entries:
        return []
    max_images = int(max_images or getattr(config, "WECHAT_QR_MAX_IMAGES", 2) or 2)
    max_candidates = int(max_candidates or getattr(config, "WECHAT_QR_MAX_CANDIDATES", 6) or 6)
    if max_images <= 0 or max_candidates <= 0:
        return []
    image_dir = _image_dir()
    results = []
    seen = set()
    for entry in entries:
        if len(results) >= max_images or max_candidates <= 0:
            break
        src = str(entry.get("src") or "").strip()
        ctx = str(entry.get("ctx") or "")
        if not src or src.startswith("data:") or "wx_fmt=gif" in src:
            continue
        if not QR_CONTEXT_RE.search(ctx):
            continue
        max_candidates -= 1
        data, content_type = _download(src)
        if not data:
            continue
        is_qr, decoded = detect_qr(data)
        if not is_qr:
            continue
        digest = hashlib.sha1(src.encode("utf-8")).hexdigest()[:16]
        if digest in seen:
            continue
        seen.add(digest)
        ext = _EXT_BY_TYPE.get(str(content_type).split(";")[0].strip().lower(), "")
        if not ext:
            match = re.search(r"wx_fmt=(\w+)", src)
            ext = (match.group(1) if match else "jpg").lower()
            ext = {"jpeg": "jpg"}.get(ext, ext)
        path = os.path.join(image_dir, f"qrcode_{digest}.{ext}")
        try:
            with open(path, "wb") as handle:
                handle.write(data)
        except Exception:
            continue
        alt = _alt_for(decoded, ctx)
        results.append({"path": path.replace("\\", "/"), "alt": alt, "decoded": decoded})
        print(f"公众号：识别到{alt}")
    return results
