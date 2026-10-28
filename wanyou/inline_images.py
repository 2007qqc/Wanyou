"""把复制源里的本地图片压成 ``data:`` URI，让「一键复制」不依赖任何上传。

公众号和秀米只接受它们自己拉得到的图片地址：``http(s)://`` 或内联 ``data:``。
复制源里指向本机文件的 ``<img src="E:/…">`` 粘过去必然断图，而让用户手动重传
六张海报正是这个按钮想省掉的事。

所以导出时把本地图片读出来、最长边缩到 ``max_dimension``、重新编码后内嵌。
缩图是有意的：原图合计 12 MB，base64 还要再涨三分之一，粘进编辑器会明显卡；
压到 1000px 长边后一套约 1 MB，视觉上和原图没有可辨差别。
"""

from __future__ import annotations

import base64
import io
import os
import re
from typing import Dict, Tuple

try:  # 缩图依赖 Pillow；没装就退化成「只嵌入不缩放」，不让导出直接失败
    from PIL import Image
except Exception:  # pragma: no cover - 运行环境缺 Pillow 时
    Image = None  # type: ignore[assignment]


_IMG_TAG_RE = re.compile(r"<img\b[^>]*?>", re.I)
_SRC_ATTR_RE = re.compile(r"""\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)

DEFAULT_MAX_DIMENSION = 900
DEFAULT_MAX_TOTAL_BYTES = 6 * 1024 * 1024
DEFAULT_QUALITY = 80


def _local_path(src: str, base_dir: str) -> str:
    """把 src 解析成本机文件路径；不是本地文件就返回空串。"""

    value = (src or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered.startswith(("data:", "http://", "https://", "//", "blob:")):
        return ""

    path = value
    if lowered.startswith("file:///"):
        path = value[8:]
    elif lowered.startswith("file://"):
        path = value[7:]
    path = path.replace("/", os.sep)
    if not os.path.isabs(path):
        if not base_dir:
            return ""
        path = os.path.join(base_dir, path)
    return path if os.path.isfile(path) else ""


def _has_real_alpha(image: "Image.Image") -> bool:
    """真的用到透明通道吗？很多 .jpg 被 Pillow 读成 RGBA，其实没有透明度。"""

    if image.mode not in ("RGBA", "LA", "P"):
        return False
    if image.mode == "P":
        return "transparency" in image.info
    alpha = image.convert("RGBA").getchannel("A")
    return alpha.getextrema()[0] < 255


def _flatten_on_white(image: "Image.Image") -> "Image.Image":
    background = Image.new("RGB", image.size, (255, 255, 255))
    rgba = image.convert("RGBA")
    background.paste(rgba, mask=rgba.split()[3])
    return background


def _encode_image(path: str, max_dimension: int, quality: int) -> Tuple[str, bytes]:
    """读图 → 缩到最长边 max_dimension → 返回 (mime, 编码后的字节)。

    照片一律走 JPEG：1000px 的 JPEG 约 200 KB，同样的图存 PNG 会到 1.5 MB，
    粘进编辑器直接卡住。只有真带透明的图才保留 PNG。
    """

    original_bytes = os.path.getsize(path)
    if Image is None:
        with open(path, "rb") as handle:
            payload = handle.read()
        return _guess_mime(path), payload

    extension = os.path.splitext(path)[1].lower()

    with Image.open(path) as image:
        image.load()
        width, height = image.size
        longest = max(width, height)
        if longest > max_dimension:
            scale = max_dimension / float(longest)
            image = image.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.LANCZOS,
            )

        # 扩展名已经是照片格式的，直接按 JPEG 出；其余看是否真带透明
        keep_alpha = extension not in (".jpg", ".jpeg", ".bmp") and _has_real_alpha(image)

        buffer = io.BytesIO()
        if keep_alpha:
            image.convert("RGBA").save(buffer, format="PNG", optimize=True)
            mime = "image/png"
        else:
            if image.mode != "RGB":
                image = _flatten_on_white(image) if image.mode in ("RGBA", "LA", "P") else image.convert("RGB")
            image.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
            mime = "image/jpeg"

    payload = buffer.getvalue()
    # 压完反而更大（小图/已压缩过的 PNG）就退回原文件
    if len(payload) >= original_bytes:
        with open(path, "rb") as handle:
            return _guess_mime(path), handle.read()
    return mime, payload


def _guess_mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(ext, "image/png")


def embed_local_images(
    html_text: str,
    base_dir: str = "",
    max_dimension: int = DEFAULT_MAX_DIMENSION,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    quality: int = DEFAULT_QUALITY,
) -> Tuple[str, Dict[str, object]]:
    """把 HTML 里指向本机文件的 <img> 换成内联 data: URI。

    返回 ``(新 HTML, 统计)``。统计里的 ``remaining_local`` 是仍然没能内嵌的
    张数——只有它非零时粘贴才真的会断图，按钮据此提示用户。
    """

    stats: Dict[str, object] = {
        "embedded": 0,
        "skipped": 0,
        "source_bytes": 0,
        "payload_bytes": 0,
        "remaining_local": 0,
        "names": [],
    }
    if not html_text:
        return html_text, stats

    def replace_tag(match: "re.Match[str]") -> str:
        tag = match.group(0)
        src_match = _SRC_ATTR_RE.search(tag)
        if not src_match:
            return tag
        src = src_match.group(1) if src_match.group(1) is not None else (src_match.group(2) or "")
        path = _local_path(src, base_dir)
        if not path:
            return tag

        if int(stats["payload_bytes"]) >= max_total_bytes:
            stats["skipped"] = int(stats["skipped"]) + 1
            stats["remaining_local"] = int(stats["remaining_local"]) + 1
            return tag

        try:
            mime, payload = _encode_image(path, max_dimension, quality)
        except Exception:
            stats["skipped"] = int(stats["skipped"]) + 1
            stats["remaining_local"] = int(stats["remaining_local"]) + 1
            return tag

        data_uri = "data:%s;base64,%s" % (mime, base64.b64encode(payload).decode("ascii"))
        stats["embedded"] = int(stats["embedded"]) + 1
        stats["source_bytes"] = int(stats["source_bytes"]) + os.path.getsize(path)
        stats["payload_bytes"] = int(stats["payload_bytes"]) + len(payload)
        names = stats["names"]
        if isinstance(names, list):
            names.append(os.path.basename(path))
        return tag[: src_match.start()] + 'src="%s"' % data_uri + tag[src_match.end():]

    replaced = _IMG_TAG_RE.sub(replace_tag, html_text)
    return replaced, stats
