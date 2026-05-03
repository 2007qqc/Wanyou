import argparse
import html
import json
import mimetypes
import os
import pathlib
import re
import sys

try:
    import winreg
except Exception:
    winreg = None

from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from generators.wechat_inline import markdown_to_wechat_inline_html
from wanyou.env_loader import load_project_env

load_project_env()

TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
UPLOAD_IMG_URL = "https://api.weixin.qq.com/cgi-bin/media/uploadimg"
ADD_MATERIAL_URL = "https://api.weixin.qq.com/cgi-bin/material/add_material"
ADD_DRAFT_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"
MAX_TITLE_CHARS = 32
MAX_TITLE_BYTES = 64
MAX_AUTHOR_CHARS = 4
MAX_AUTHOR_BYTES = 12
MAX_DIGEST_BYTES = 120
MAX_DIGEST_CHARS = 54
MAX_SOURCE_URL_CHARS = 1024
MAX_CONTENT_CHARS = 19000
MAX_CONTENT_BYTES_WARNING = 900000


class MainExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.depth = 0
        self.capture = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "main" and "page" in attrs_dict.get("class", "").split():
            self.capture = True
            self.depth = 1
            self.parts.append(self.get_starttag_text() or "<main>")
            return
        if self.capture:
            self.depth += 1
            self.parts.append(self.get_starttag_text() or f"<{tag}>")

    def handle_startendtag(self, tag, attrs):
        if self.capture:
            self.parts.append(self.get_starttag_text() or f"<{tag} />")

    def handle_endtag(self, tag):
        if not self.capture:
            return
        self.parts.append(f"</{tag}>")
        self.depth -= 1
        if self.depth <= 0:
            self.capture = False

    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)

    def handle_entityref(self, name):
        if self.capture:
            self.parts.append(f"&{name};")

    def handle_charref(self, name):
        if self.capture:
            self.parts.append(f"&#{name};")


def _configure_console():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    if winreg is None:
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _value_type = winreg.QueryValueEx(key, name)
    except Exception:
        return ""
    return str(value or "").strip()


def _env_diagnostic(name: str) -> str:
    process_has = bool(os.getenv(name, "").strip())
    user_has = False
    if winreg is not None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value, _value_type = winreg.QueryValueEx(key, name)
                user_has = bool(str(value or "").strip())
        except Exception:
            user_has = False
    return f"{name}: process={'yes' if process_has else 'no'}, user={'yes' if user_has else 'no'}"


def get_access_token(appid: str, appsecret: str, timeout: int) -> str:
    resp = requests.get(
        TOKEN_URL,
        params={"grant_type": "client_credential", "appid": appid, "secret": appsecret},
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    token = payload.get("access_token")
    if not token:
        raise RuntimeError(f"获取 access_token 失败: {json.dumps(payload, ensure_ascii=False)}")
    return token


def extract_wechat_content(html_text: str) -> str:
    parser = MainExtractor()
    parser.feed(html_text or "")
    content = "".join(parser.parts).strip()
    if not content:
        match = re.search(r"<body[^>]*>([\s\S]*?)</body>", html_text or "", flags=re.I)
        content = match.group(1).strip() if match else (html_text or "").strip()

    content = re.sub(r"<!DOCTYPE[^>]*>", "", content, flags=re.I)
    content = re.sub(r"<\/?(?:html|head|body|meta|title|link)[^>]*>", "", content, flags=re.I)
    content = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", content, flags=re.I)
    content = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", content, flags=re.I)
    content = re.sub(r"\sloading=(['\"]).*?\1", "", content, flags=re.I)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


def build_wechat_content_from_paths(html_path: pathlib.Path, markdown_override: str = "") -> tuple[str, pathlib.Path]:
    markdown_path = pathlib.Path(markdown_override).resolve() if markdown_override else html_path.with_suffix(".md")
    if markdown_path.exists():
        markdown_text = markdown_path.read_text(encoding="utf-8")
        print(f"wechat_inline_source: {markdown_path}")
        return markdown_to_wechat_inline_html(markdown_text, markdown_path=str(markdown_path)), markdown_path

    content, asset_base_path = build_wechat_content_from_paths(html_path, args.markdown)
    return extract_wechat_content(html_text), html_path


def _is_remote_url(src: str) -> bool:
    return bool(re.match(r"^(https?:)?//", src or "", flags=re.I))


def _resolve_image_path(src: str, html_path: pathlib.Path) -> pathlib.Path:
    cleaned = html.unescape(src or "").strip().strip("'").strip('"')
    cleaned = cleaned.split("?", 1)[0]
    candidate = pathlib.Path(cleaned)
    if candidate.is_absolute():
        return candidate
    return (html_path.parent / candidate).resolve()


def upload_inline_image(access_token: str, image_path: pathlib.Path, timeout: int) -> str:
    if not image_path.exists():
        raise FileNotFoundError(f"正文图片不存在: {image_path}")
    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/jpeg"
    with image_path.open("rb") as fh:
        resp = requests.post(
            UPLOAD_IMG_URL,
            params={"access_token": access_token},
            files={"media": (image_path.name, fh, mime_type)},
            timeout=timeout,
        )
    resp.raise_for_status()
    payload = resp.json()
    url = payload.get("url")
    if not url:
        raise RuntimeError(f"上传正文图片失败 {image_path}: {json.dumps(payload, ensure_ascii=False)}")
    return url


def find_first_local_image(content: str, asset_base_path: pathlib.Path) -> pathlib.Path | None:
    for match in re.finditer(r"src=([\'\"])(.*?)\1", content or "", flags=re.I):
        src = match.group(2)
        if _is_remote_url(src) or src.startswith("data:"):
            continue
        image_path = _resolve_image_path(src, asset_base_path)
        if image_path.exists():
            return image_path
    return None


def upload_cover(access_token: str, cover_path: pathlib.Path, timeout: int) -> str:
    if not cover_path.exists():
        raise FileNotFoundError(f"封面图不存在: {cover_path}")
    mime_type = mimetypes.guess_type(str(cover_path))[0] or "image/jpeg"
    with cover_path.open("rb") as fh:
        resp = requests.post(
            ADD_MATERIAL_URL,
            params={"access_token": access_token, "type": "image"},
            files={"media": (cover_path.name, fh, mime_type)},
            timeout=timeout,
        )
    resp.raise_for_status()
    payload = resp.json()
    media_id = payload.get("media_id")
    if not media_id:
        raise RuntimeError(f"上传封面图失败: {json.dumps(payload, ensure_ascii=False)}")
    return media_id


def replace_local_images(content: str, html_path: pathlib.Path, access_token: str, timeout: int, dry_run: bool) -> str:
    cache = {}

    def repl(match):
        quote = match.group(1)
        src = match.group(2)
        if _is_remote_url(src) or src.startswith("data:"):
            return match.group(0)
        image_path = _resolve_image_path(src, html_path)
        if dry_run:
            print(f"dry-run: 将上传正文图片 {image_path}")
            new_src = src
        else:
            if image_path not in cache:
                cache[image_path] = upload_inline_image(access_token, image_path, timeout)
                print(f"已上传正文图片: {image_path.name}")
            new_src = cache[image_path]
        return f"src={quote}{html.escape(new_src, quote=True)}{quote}"

    return re.sub(r"src=(['\"])(.*?)\1", repl, content, flags=re.I)


def _fit_text_limit(value: str, *, max_chars: int, max_bytes: int, fallback: str = "") -> str:
    text = _decode_literal_unicode_escapes(value)
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    if not text:
        text = fallback
    if max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars].rstrip()
    while max_bytes > 0 and len(text.encode("utf-8")) > max_bytes and text:
        text = text[:-1].rstrip()
    return text or fallback


def _decode_literal_unicode_escapes(value: str) -> str:
    text = str(value or "")
    if "\\u" not in text:
        return text

    def repl(match):
        try:
            return chr(int(match.group(1), 16))
        except Exception:
            return match.group(0)

    return re.sub(r"\\u([0-9a-fA-F]{4})", repl, text)


def _sanitize_author(value: str) -> str:
    text = _decode_literal_unicode_escapes(value)
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    if not text:
        return ""
    if len(text) > MAX_AUTHOR_CHARS or len(text.encode("utf-8")) > MAX_AUTHOR_BYTES:
        text = text[:MAX_AUTHOR_CHARS].rstrip()
        while len(text.encode("utf-8")) > MAX_AUTHOR_BYTES and text:
            text = text[:-1].rstrip()
        print("author_truncated: author was shortened for WeChat limits")
    return text


def _sanitize_source_url(url: str) -> str:
    text = _decode_literal_unicode_escapes(url).strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        print("source_url_invalid: ignored non-http source URL")
        return ""
    return text[:MAX_SOURCE_URL_CHARS]


def _truncate_content(content: str) -> str:
    text = _decode_literal_unicode_escapes(content)
    # Temporarily keep the full article body. We still print content length before
    # submission so oversized drafts can be diagnosed without silently truncating.
    return text

def sanitize_article_fields(article: dict) -> dict:
    sanitized = dict(article)
    sanitized["title"] = _fit_text_limit(
        sanitized.get("title", ""),
        max_chars=MAX_TITLE_CHARS,
        max_bytes=MAX_TITLE_BYTES,
        fallback="\u4e07\u6709\u9884\u62a5",
    )
    sanitized["author"] = _sanitize_author(sanitized.get("author", ""))
    sanitized["digest"] = _truncate_digest(sanitized.get("digest", ""))
    sanitized["content"] = _truncate_content(sanitized.get("content", ""))
    sanitized["content_source_url"] = _sanitize_source_url(sanitized.get("content_source_url", ""))
    return sanitized


def print_article_field_lengths(article: dict):
    for key in ("title", "author", "digest", "content_source_url", "content"):
        value = str(article.get(key) or "")
        print(f"{key}_length: {len(value)} chars / {len(value.encode('utf-8'))} UTF-8 bytes")
    content_bytes = len(str(article.get("content") or "").encode("utf-8"))
    if content_bytes > MAX_CONTENT_BYTES_WARNING:
        print(f"content_size_warning: content is {content_bytes} bytes; WeChat may reject very large articles")


def _draft_error_hint(payload: dict) -> str:
    errcode = payload.get("errcode")
    errmsg = str(payload.get("errmsg") or "")
    if errcode == 45003 or "title size out of limit" in errmsg:
        return "\u6807\u9898\u5b57\u6bb5\u8d85\u9650\uff0c\u8bf7\u7f29\u77ed --title\u3002"
    if errcode == 45004 or "description size out of limit" in errmsg:
        return "\u6458\u8981\u5b57\u6bb5\u8d85\u9650\uff0c\u8bf7\u7f29\u77ed --digest\u3002"
    if errcode == 45005 or "url size out of limit" in errmsg:
        return "\u539f\u6587\u94fe\u63a5\u5b57\u6bb5\u8d85\u9650\uff0c\u8bf7\u7f29\u77ed\u6216\u79fb\u9664 --source-url\u3002"
    if errcode == 45110 or "author size out of limit" in errmsg:
        return "\u4f5c\u8005\u5b57\u6bb5\u8d85\u9650\uff1b\u9ed8\u8ba4\u4e0d\u63d0\u4ea4 author\uff0c\u5982\u663e\u5f0f\u4f20\u5165 --author\uff0c\u8bf7\u6539\u7528 4 \u4e2a\u4e2d\u6587\u5b57\u4ee5\u5185\u7684\u77ed\u540d\u3002"
    if "size out of limit" in errmsg:
        return "\u5fae\u4fe1\u8fd4\u56de\u5b57\u6bb5\u957f\u5ea6\u8d85\u9650\uff0c\u8bf7\u68c0\u67e5\u811a\u672c\u6253\u5370\u7684 title/author/digest/source_url/content \u957f\u5ea6\u3002"
    return ""


def create_draft(access_token: str, article: dict, timeout: int) -> dict:
    body = json.dumps({"articles": [article]}, ensure_ascii=False).encode("utf-8")
    resp = requests.post(
        ADD_DRAFT_URL,
        params={"access_token": access_token},
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("errcode") not in (None, 0):
        raise RuntimeError(f"创建草稿失败: {json.dumps(payload, ensure_ascii=False)}")
    if not payload.get("media_id"):
        raise RuntimeError(f"创建草稿未返回 media_id: {json.dumps(payload, ensure_ascii=False)}")
    return payload


def _truncate_digest(text: str) -> str:
    cleaned = _decode_literal_unicode_escapes(text)
    cleaned = html.unescape(re.sub(r"\s+", " ", cleaned)).strip()
    # Remove fixed H5 theme boilerplate before building the WeChat description.
    cleaned = re.sub(
        r"^(\u6e05\u7269\u8bed\s*[\u00b7\u30fb]\s*\u7269\u7406\u7cfb\u98ce\u683c\s*)?\u4e07\u6709\u9884\u62a5\s*",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"\u53c2\u8003\u4eba\u5de5\u7f16\u8f91\u7248\u4e07\u6709\u9884\u62a5\u7684\u516c\u4f17\u53f7\u6392\u7248\u8282\u594f[^\u3002]*\u3002",
        "",
        cleaned,
    )
    cleaned = cleaned.replace(
        "\u5929\u6c14\u6e10\u6696\uff0c\u5927\u5bb6\u6ce8\u610f\u589e\u51cf\u8863\u7269\u3002",
        "",
    ).strip()
    if len(cleaned) > MAX_DIGEST_CHARS:
        cleaned = cleaned[:MAX_DIGEST_CHARS].rstrip() + "..."
    while len(cleaned.encode("utf-8")) > MAX_DIGEST_BYTES and cleaned:
        cleaned = cleaned[:-1].rstrip()
    return cleaned or "\u672c\u671f\u4e07\u6709\u9884\u62a5\u5df2\u6574\u7406\u5b8c\u6210\u3002"

def infer_digest(content: str, explicit: str) -> str:
    if explicit:
        return _truncate_digest(explicit)
    return _truncate_digest("\u672c\u671f\u4e07\u6709\u9884\u62a5\u5df2\u6574\u7406\u5b8c\u6210\u3002")


def main():
    _configure_console()
    parser = argparse.ArgumentParser(description="Create a WeChat Official Account draft from Wanyou HTML.")
    parser.add_argument("html", help="Path to Wanyou HTML output. If a same-name .md exists, it is used to build inline WeChat HTML.")
    parser.add_argument("--markdown", default="", help="Optional final Markdown path used to build WeChat inline HTML.")
    parser.add_argument("--title", default="万有预报", help="Draft article title.")
    parser.add_argument("--author", default="", help="Draft article author. Empty by default to avoid WeChat author limit errors.")
    parser.add_argument("--digest", default="", help="Draft digest. Defaults to text extracted from content.")
    parser.add_argument("--source-url", default="", help="Original article source URL.")
    parser.add_argument("--cover", default="", help="Optional cover image path. If omitted, the first local content image is used when available.")
    parser.add_argument("--appid-env", default="WECHAT_MP_APPID", help="Environment variable for official account AppID.")
    parser.add_argument("--secret-env", default="WECHAT_MP_APPSECRET", help="Environment variable for official account AppSecret.")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds.")
    parser.add_argument("--dry-run", action="store_true", help="Build and validate payload without calling WeChat APIs.")
    args = parser.parse_args()

    html_path = pathlib.Path(args.html).resolve()
    cover_path = pathlib.Path(args.cover).resolve() if args.cover else None
    content, asset_base_path = build_wechat_content_from_paths(html_path, args.markdown)

    if not content:
        raise SystemExit("HTML 正文为空，无法创建草稿。")

    access_token = ""
    if not args.dry_run:
        appid = _env(args.appid_env)
        appsecret = _env(args.secret_env)
        if not appid or not appsecret:
            diagnostics = "; ".join([_env_diagnostic(args.appid_env), _env_diagnostic(args.secret_env)])
            raise SystemExit(
                f"\u8bf7\u5148\u8bbe\u7f6e\u516c\u4f17\u53f7\u73af\u5883\u53d8\u91cf {args.appid_env} \u548c {args.secret_env}\u3002"
                f" \u5f53\u524d\u68c0\u6d4b\u7ed3\u679c\uff1a{diagnostics}\u3002"
                "\u6ce8\u610f\uff1a\u4fdd\u5b58\u516c\u4f17\u53f7\u8349\u7a3f\u9700\u8981\u516c\u4f17\u53f7\u5b98\u65b9 AppID/AppSecret\uff0c\u4e0d\u662f WECHAT_PUBLIC_API_KEY\u3002"
            )
        access_token = get_access_token(appid, appsecret, args.timeout)
        print("已获取公众号 access_token")

    content = replace_local_images(content, asset_base_path, access_token, args.timeout, args.dry_run)

    if cover_path is None:
        cover_path = find_first_local_image(content, asset_base_path)
        if cover_path:
            print(f"cover_auto_selected: {cover_path}")

    if args.dry_run:
        thumb_media_id = "DRY_RUN_THUMB_MEDIA_ID"
        if cover_path:
            print(f"dry-run: \u5c06\u4e0a\u4f20\u5c01\u9762\u56fe {cover_path}")
        else:
            print("dry-run: \u672a\u6307\u5b9a\u5c01\u9762\uff0c\u4e5f\u672a\u627e\u5230\u53ef\u7528\u6b63\u6587\u56fe\u7247\uff1b\u6b63\u5f0f\u4fdd\u5b58\u65f6\u5fae\u4fe1\u53ef\u80fd\u8981\u6c42\u5c01\u9762\u56fe")
    else:
        if cover_path is None:
            raise SystemExit("\u672a\u6307\u5b9a\u5c01\u9762\uff0c\u4e5f\u672a\u627e\u5230\u53ef\u7528\u6b63\u6587\u56fe\u7247\u3002\u5fae\u4fe1\u516c\u4f17\u53f7\u8349\u7a3f\u63a5\u53e3\u901a\u5e38\u8981\u6c42 thumb_media_id\uff0c\u8bf7\u7528 --cover \u6307\u5b9a\u5c01\u9762\u56fe\u3002")
        thumb_media_id = upload_cover(access_token, cover_path, args.timeout)
        print("\u5df2\u4e0a\u4f20\u5c01\u9762\u56fe")
        print("已上传封面图")

    digest = infer_digest(content, args.digest)

    article = sanitize_article_fields(
        {
            "title": args.title,
            "author": args.author,
            "digest": digest,
            "content": content,
            "content_source_url": args.source_url,
            "thumb_media_id": thumb_media_id,
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        }
    )
    if not article.get("author"):
        article.pop("author", None)
    print_article_field_lengths(article)

    if args.dry_run:
        preview_path = html_path.with_name(html_path.stem + "_wechat_draft_payload.json")
        preview_path.write_text(json.dumps({"articles": [article]}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"dry_run_payload_path: {preview_path}")
        return

    payload = create_draft(access_token, article, args.timeout)
    print(f"draft_media_id: {payload['media_id']}")
    print("草稿已保存到微信公众号后台，请先预览确认后再发布。")


if __name__ == "__main__":
    main()
