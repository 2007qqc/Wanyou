import argparse
import base64
import json
import mimetypes
import os
import pathlib
import re
import shutil
import sys
import tempfile
import time
import traceback

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from generators.wechat_inline import markdown_to_wechat_inline_html
from wanyou.browser import browser_supports_profile_dir, get_selenium_browser_name, make_browser_options, make_webdriver

_XIUMI_DEBUG_LOG_PATH = None


def _configure_console():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _xiumi_debug_log_path() -> pathlib.Path:
    global _XIUMI_DEBUG_LOG_PATH
    if _XIUMI_DEBUG_LOG_PATH is None:
        log_dir = ROOT / "output" / "xiumi_debug"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        _XIUMI_DEBUG_LOG_PATH = log_dir / f"xiumi_upload_{stamp}.jsonl"
    return _XIUMI_DEBUG_LOG_PATH


def _log_xiumi_debug(event: str, **data):
    try:
        payload = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": event,
            **data,
        }
        path = _xiumi_debug_log_path()
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _extract_main_html(html_text: str) -> str:
    match = re.search(r"<main[^>]*class=[\"'][^\"']*page[^\"']*[\"'][^>]*>([\s\S]*?)</main>", html_text or "", flags=re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r"<body[^>]*>([\s\S]*?)</body>", html_text or "", flags=re.I)
    if match:
        return match.group(1).strip()
    return (html_text or "").strip()


def _resolve_content_paths(html_path: pathlib.Path, markdown_override: str = "") -> tuple[str, pathlib.Path]:
    markdown_path = pathlib.Path(markdown_override).resolve() if markdown_override else html_path.with_suffix(".md")
    if markdown_path.exists():
        markdown_text = markdown_path.read_text(encoding="utf-8")
        _log_xiumi_debug("xiumi_source_markdown", path=str(markdown_path))
        return markdown_to_wechat_inline_html(markdown_text, markdown_path=str(markdown_path)), markdown_path

    html_text = html_path.read_text(encoding="utf-8")
    _log_xiumi_debug("xiumi_source_html", path=str(html_path))
    return _extract_main_html(html_text), html_path


def _guess_mime_type(path: pathlib.Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def _image_file_to_data_url(path: pathlib.Path) -> str:
    mime_type = _guess_mime_type(path)
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{data}"


def _inline_local_images(html_text: str, asset_base_path: pathlib.Path) -> str:
    def repl(match):
        quote = match.group(1)
        src = (match.group(2) or "").strip()
        if not src or re.match(r"^(?:https?:)?//|^data:", src, flags=re.I):
            return match.group(0)
        cleaned = src.split("?", 1)[0].strip().strip("'").strip('"')
        candidate = pathlib.Path(cleaned)
        if not candidate.is_absolute():
            candidate = (asset_base_path.parent / candidate).resolve()
        if not candidate.exists():
            return match.group(0)
        data_url = _image_file_to_data_url(candidate)
        return f'src={quote}{data_url}{quote}'

    return re.sub(r"src=(['\"])(.*?)\1", repl, html_text or "", flags=re.I)


def _is_remote_image_src(src: str) -> bool:
    return bool(re.match(r"^(?:https?:)?//", str(src or ""), flags=re.I))


def _is_data_image_src(src: str) -> bool:
    return str(src or "").startswith("data:")


def _image_payload_stats(html_text: str) -> dict:
    srcs = re.findall(r"<img\b[^>]*\bsrc=(['\"])(.*?)\1", html_text or "", flags=re.I)
    data_urls = [src for _quote, src in srcs if _is_data_image_src(src)]
    local_urls = [
        src
        for _quote, src in srcs
        if src and not _is_data_image_src(src) and not _is_remote_image_src(src)
    ]
    return {
        "html_chars": len(html_text or ""),
        "image_count": len(srcs),
        "data_image_count": len(data_urls),
        "local_image_count": len(local_urls),
        "data_image_chars": sum(len(src) for src in data_urls),
    }


def _local_image_sources(html_text: str) -> list[str]:
    srcs = re.findall(r"<img\b[^>]*\bsrc=(['\"])(.*?)\1", html_text or "", flags=re.I)
    return [
        src
        for _quote, src in srcs
        if src and not _is_data_image_src(src) and not _is_remote_image_src(src)
    ]


def _remove_images_for_xiumi(html_text: str) -> str:
    removed = 0

    def repl(match):
        nonlocal removed
        removed += 1
        return "<p style=\"margin:8px 0;color:#8a7c58;font-size:14px;\">[配图已保留在本地 HTML，秀米草稿中未自动内联]</p>"

    cleaned = re.sub(r"<img\b[^>]*>", repl, html_text or "", flags=re.I)
    cleaned = re.sub(r"<section\b([^>]*)>\s*(?:<p[^>]*>\[配图已保留在本地 HTML，秀米草稿中未自动内联\]</p>\s*)+</section>", "", cleaned, flags=re.I)
    _log_xiumi_debug("xiumi_image_mode_omit_count", removed=removed)
    return cleaned


def _remove_unuploaded_images_for_xiumi(html_text: str) -> str:
    removed = 0

    def repl(match):
        nonlocal removed
        tag = match.group(0)
        src_match = re.search(r"\bsrc=(['\"])(.*?)\1", tag, flags=re.I)
        src = (src_match.group(2) if src_match else "").strip()
        if src and _is_remote_image_src(src):
            return tag
        removed += 1
        return "<p style=\"margin:8px 0;color:#8a7c58;font-size:14px;\">[配图上传未完成，请在秀米图库中手动补充]</p>"

    cleaned = re.sub(r"<img\b[^>]*>", repl, html_text or "", flags=re.I)
    _log_xiumi_debug("xiumi_unuploaded_image_omit_count", removed=removed)
    return cleaned


def _replace_images_with_placeholders_for_xiumi(html_text: str) -> str:
    mode = str(getattr(config, "XIUMI_IMAGE_MODE", "upload") or "upload").strip().lower()
    if mode != "upload":
        return html_text

    index = 0

    def repl(match):
        nonlocal index
        index += 1
        return (
            "<p "
            f"data-wanyou-image-placeholder=\"{index}\" "
            "style=\"margin:8px 0;color:#8a7c58;font-size:14px;\">"
            "[配图上传中]"
            "</p>"
        )

    prepared = re.sub(r"<img\b[^>]*>", repl, html_text or "", flags=re.I)
    if index:
        _log_xiumi_debug("text_first_image_placeholders", count=index)
    return prepared


def _prepare_xiumi_images(html_text: str, asset_base_path: pathlib.Path) -> str:
    mode = str(getattr(config, "XIUMI_IMAGE_MODE", "upload") or "upload").strip().lower()
    if mode not in {"upload", "auto", "inline", "omit"}:
        mode = "upload"

    before = _image_payload_stats(html_text)
    _log_xiumi_debug("xiumi_image_payload_before", **before)

    if mode == "omit":
        _log_xiumi_debug("xiumi_image_mode", mode="omit")
        return _remove_images_for_xiumi(html_text)

    if mode == "upload":
        local_images = _local_image_sources(html_text)
        data_images = before["data_image_count"]
        if local_images or data_images:
            _log_xiumi_debug("xiumi_image_mode", mode="upload_pending", local_images=len(local_images), data_images=data_images)
            return html_text
        _log_xiumi_debug("xiumi_image_mode", mode="upload_no_images")
        return html_text

    inlined = _inline_local_images(html_text, asset_base_path)
    after = _image_payload_stats(inlined)
    _log_xiumi_debug("xiumi_image_payload_after_inline", **after)

    max_chars = int(getattr(config, "XIUMI_MAX_INLINE_IMAGE_HTML_CHARS", 900000) or 0)
    if mode == "auto" and max_chars and after["html_chars"] > max_chars:
        _log_xiumi_debug("xiumi_image_mode", mode="auto_omit", html_chars=after["html_chars"], max_chars=max_chars)
        return _remove_images_for_xiumi(html_text)

    _log_xiumi_debug("xiumi_image_mode", mode=f"{mode}_inline")
    return inlined


def _first_heading(markdown_text: str) -> str:
    for line in (markdown_text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _first_summary_line(markdown_text: str) -> str:
    for line in (markdown_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("!"):
            continue
        stripped = re.sub(r"\s+", " ", stripped)
        return stripped[:120]
    return ""


def _make_xiumi_browser(profile_dir: pathlib.Path, *, detach: bool = False):
    os.makedirs(config.SELENIUM_CACHE_DIR, exist_ok=True)
    os.environ.setdefault("SE_CACHE_PATH", os.path.abspath(config.SELENIUM_CACHE_DIR))

    browser_name = get_selenium_browser_name()
    if browser_supports_profile_dir(browser_name):
        profile_dir.mkdir(parents=True, exist_ok=True)
    options = make_browser_options(browser_name, str(profile_dir), headless=False, detach=detach)
    browser = make_webdriver(browser_name, options)
    browser._wanyou_browser_name = browser_name
    if getattr(config, "PAGE_LOAD_TIMEOUT", 0):
        browser.set_page_load_timeout(config.PAGE_LOAD_TIMEOUT)
    return browser


def _cleanup_profile_dir(profile_dir: pathlib.Path, retries: int = 5, delay_seconds: float = 1.0) -> bool:
    if not profile_dir.exists():
        return True
    for _ in range(max(1, retries)):
        try:
            shutil.rmtree(profile_dir)
            return True
        except Exception:
            time.sleep(delay_seconds)
    return not profile_dir.exists()


def _wait_for_user_before_closing_browser():
    if not getattr(sys.stdin, "isatty", lambda: False)():
        print("秀米：当前不是交互式命令行，跳过编辑等待并关闭浏览器。")
        return
    print("秀米：浏览器将保持打开，方便你继续检查或微调。确认已在秀米保存后，回到命令行按回车关闭浏览器并结束程序。")
    try:
        input()
    except EOFError:
        print("秀米：命令行输入已关闭，继续关闭浏览器。")


def _wait_editor_ready(browser, timeout: int):
    WebDriverWait(browser, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")
    WebDriverWait(browser, timeout).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "button.btn-img.op-btn.save")) > 0)
    WebDriverWait(browser, timeout).until(lambda d: len(d.find_elements(By.XPATH, '//*[@contenteditable="true"]')) > 0)


def _visible_login_links(browser):
    links = []
    selectors = [
        (By.CSS_SELECTOR, "a.usr-sign-in"),
        (By.XPATH, "//*[self::a or self::button][contains(normalize-space(.), '登录') or contains(normalize-space(.), '登陆')]"),
    ]
    for by, value in selectors:
        for el in browser.find_elements(by, value):
            try:
                if el.is_displayed() and el not in links:
                    links.append(el)
            except Exception:
                continue
    return links


def _wait_for_manual_login(browser, timeout: int):
    links = _visible_login_links(browser)
    if links:
        try:
            links[0].click()
        except Exception:
            pass
        print("秀米：请在打开的浏览器中完成登录。程序会自动检测登录状态并继续，无需回终端按回车。")
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not _visible_login_links(browser):
                return True
            time.sleep(1)
    return not _visible_login_links(browser)


def _click_xiumi_create_candidate(browser, include_terms: list[str], *, exclude_terms: list[str] | None = None) -> dict:
    script = """
const includeTerms = arguments[0].map(t => String(t).toLowerCase());
const excludeTerms = arguments[1].map(t => String(t).toLowerCase());
function visible(el) {
  const style = window.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  return style && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
}
function haystack(el) {
  return [
    el.innerText, el.textContent, el.title, el.alt, el.getAttribute('aria-label'),
    el.id, el.className, el.getAttribute('data-title'), el.getAttribute('data-name')
  ].join(' ').replace(/\\s+/g, ' ').trim().toLowerCase();
}
const selector = [
  'button', 'a', 'li', 'div', 'span', '[role="button"]', '[title]', '[aria-label]'
].join(',');
const candidates = Array.from(document.querySelectorAll(selector))
  .filter(el => visible(el))
  .map(el => {
    const text = haystack(el);
    let score = 0;
    let matched = false;
    for (const term of includeTerms) {
      if (!term) continue;
      if (text === term) {
        score += 50;
        matched = true;
      } else if (text.includes(term)) {
        score += 15;
        matched = true;
      }
    }
    if (!matched) return { el, score: -999, text };
    for (const term of excludeTerms) {
      if (term && text.includes(term)) score -= 60;
    }
    const tag = el.tagName.toLowerCase();
    if (tag === 'button' || tag === 'a' || tag === 'li' || el.getAttribute('role') === 'button') score += 5;
    return { el, score, text };
  })
  .filter(item => item.score > 0)
  .sort((a, b) => b.score - a.score);
for (const item of candidates.slice(0, 8)) {
  try {
    item.el.scrollIntoView({ block: 'center', inline: 'center' });
    item.el.click();
    return { clicked: true, score: item.score, text: item.text, candidates: candidates.length };
  } catch (e) {}
}
return { clicked: false, text: '', candidates: candidates.length };
"""
    try:
        return browser.execute_script(script, include_terms, exclude_terms or []) or {"clicked": False}
    except Exception as exc:
        return {"clicked": False, "error": str(exc)}


def _page_excerpt(browser, limit: int = 300) -> str:
    try:
        text = browser.execute_script("return document.body ? document.body.innerText : '';") or ""
    except Exception:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()[:limit]


def _xiumi_login_is_settling(browser) -> bool:
    excerpt = _page_excerpt(browser, 500)
    settling_terms = ["正在登录", "登录中"]
    return any(term in excerpt for term in settling_terms)


def _wait_until_xiumi_home_settled(browser, timeout: int) -> bool:
    deadline = time.time() + max(5, timeout)
    while time.time() < deadline:
        if not _visible_login_links(browser) and not _xiumi_login_is_settling(browser):
            return True
        time.sleep(1)
    return not _visible_login_links(browser) and not _xiumi_login_is_settling(browser)


def _wait_for_xiumi_login_on_home(browser, home_url: str, login_timeout: int, wait_timeout: int):
    print("秀米：正在打开“我的秀米”并确认登录状态")
    browser.get(home_url)
    WebDriverWait(browser, wait_timeout).until(lambda d: d.execute_script("return document.readyState") in ("interactive", "complete"))

    if _visible_login_links(browser):
        logged_in = _wait_for_manual_login(browser, login_timeout)
        if not logged_in:
            raise RuntimeError("秀米登录未完成，已超过等待时间。")
        browser.get(home_url)
        WebDriverWait(browser, wait_timeout).until(lambda d: d.execute_script("return document.readyState") in ("interactive", "complete"))

    if not _wait_until_xiumi_home_settled(browser, min(login_timeout, max(20, wait_timeout * 2))):
        _log_xiumi_debug("xiumi_login_not_settled", url=browser.current_url, excerpt=_page_excerpt(browser))
        raise RuntimeError("秀米登录态仍在初始化，未确认进入“我的秀米”。")
    _log_xiumi_debug("xiumi_login_confirmed", url=browser.current_url, excerpt=_page_excerpt(browser))
    print("秀米：已确认登录状态")


def _open_xiumi_editor_from_my_xiumi(browser, home_url: str, login_timeout: int, wait_timeout: int):
    _wait_for_xiumi_login_on_home(browser, home_url, login_timeout, wait_timeout)

    paper_state = _click_xiumi_create_candidate(browser, ["图文排版"], exclude_terms=["选择编辑器", "模板", "教程"])
    _log_xiumi_debug("xiumi_paper_entry_click", state=paper_state, url=browser.current_url)
    if paper_state.get("clicked"):
        print("秀米：已进入图文排版")
        time.sleep(2)

    create_steps = [
        ["新建图文", "创建图文", "新建空白图文", "空白图文"],
        ["新建", "空白"],
    ]
    exclude = ["保存", "预览", "删除", "导出", "登录", "注册", "会员", "教程", "模板", "选择编辑器", "图文排版"]
    last_state = {}
    for terms in create_steps:
        state = _click_xiumi_create_candidate(browser, terms, exclude_terms=exclude)
        last_state = state
        _log_xiumi_debug("xiumi_create_click", terms=terms, state=state, url=browser.current_url)
        if state.get("clicked"):
            print("秀米：已新建图文")
            time.sleep(1)

            type_state = _click_xiumi_create_candidate(
                browser,
                ["图文排版", "图文", "公众号图文"],
                exclude_terms=["H5", "设计", "文档", "模板", "教程", "返回", "取消"],
            )
            _log_xiumi_debug("xiumi_create_type_click", state=type_state, url=browser.current_url)
            if type_state.get("clicked"):
                print("秀米：已选择图文类型")

            deadline = time.time() + wait_timeout
            while time.time() < deadline:
                try:
                    _wait_editor_ready(browser, 2)
                    return
                except Exception:
                    time.sleep(1)

    _log_xiumi_debug("xiumi_create_failed", last_state=last_state, url=browser.current_url, excerpt=_page_excerpt(browser))
    raise RuntimeError("未能在“我的秀米”页面找到可用的新建图文入口，请检查页面状态或更新 XIUMI_HOME_URL。")


def _open_xiumi_editor(browser, home_url: str, login_timeout: int, wait_timeout: int):
    _open_xiumi_editor_from_my_xiumi(browser, home_url, login_timeout, wait_timeout)
    _wait_editor_ready(browser, wait_timeout)


def _set_input_value(browser, css_selector: str, value: str):
    if value is None:
        value = ""
    elements = browser.find_elements(By.CSS_SELECTOR, css_selector)
    if not elements:
        return
    browser.execute_script(
        """
const el = arguments[0];
const value = arguments[1];
el.value = value;
el.dispatchEvent(new Event('input', { bubbles: true }));
el.dispatchEvent(new Event('change', { bubbles: true }));
""",
        elements[0],
        value,
    )


def _set_editor_html(browser, html_text: str):
    editable = browser.find_element(By.XPATH, '//*[@contenteditable="true"]')
    return bool(browser.execute_script(
        """
const el = arguments[0];
const value = arguments[1];
var applied = false;
if (window.angular) {
  try {
    var scope = window.angular.element(el).scope();
    if (scope && scope.cell) {
      scope.$apply(function () {
        scope.cell.text = value;
      });
      applied = true;
    }
  } catch (e) {}
}
el.innerHTML = value;
el.dispatchEvent(new Event('input', { bubbles: true }));
el.dispatchEvent(new Event('change', { bubbles: true }));
return applied;
""",
        editable,
        html_text,
    ))


def _data_url_to_temp_image(src: str, temp_dir: pathlib.Path, index: int) -> pathlib.Path | None:
    match = re.match(r"^data:([^;,]+);base64,(.+)$", src or "", flags=re.I | re.S)
    if not match:
        return None
    mime_type = match.group(1).strip().lower()
    ext = mimetypes.guess_extension(mime_type) or ".png"
    if ext == ".jpe":
        ext = ".jpg"
    try:
        data = base64.b64decode(match.group(2), validate=False)
    except Exception:
        return None
    path = temp_dir / f"xiumi_inline_{index:04d}{ext}"
    path.write_bytes(data)
    return path


def _resolve_upload_image_path(src: str, asset_base_path: pathlib.Path, temp_dir: pathlib.Path, index: int) -> pathlib.Path | None:
    if _is_data_image_src(src):
        return _data_url_to_temp_image(src, temp_dir, index)
    if not src or _is_remote_image_src(src):
        return None
    cleaned = str(src).split("?", 1)[0].strip().strip("'").strip('"')
    path = pathlib.Path(cleaned)
    if not path.is_absolute():
        path = (asset_base_path.parent / path).resolve()
    return path if path.exists() else None


def _image_sources_for_upload(html_text: str, asset_base_path: pathlib.Path, temp_dir: pathlib.Path) -> list[tuple[str, pathlib.Path]]:
    result = []
    seen = set()
    for index, src in enumerate(re.findall(r"<img\b[^>]*\bsrc=(?:['\"])(.*?)(?:['\"])", html_text or "", flags=re.I), start=1):
        if not src or _is_remote_image_src(src) or src in seen:
            continue
        path = _resolve_upload_image_path(src, asset_base_path, temp_dir, index)
        if path and path.exists():
            # Upload normal local assets before data URLs; Xiumi's COS endpoint
            # is less tolerant of converted inline images.
            result.append((_is_data_image_src(src), index, src, path))
            seen.add(src)
    result.sort(key=lambda item: (item[0], item[1]))
    return [(src, path) for _is_data, _index, src, path in result]


def _remote_image_sources_ordered(browser) -> list[str]:
    try:
        values = browser.execute_script(
            """
const values = [];
for (const img of Array.from(document.querySelectorAll('img'))) {
  values.push(img.getAttribute('src') || '');
}
for (const el of Array.from(document.querySelectorAll('*'))) {
  const bg = window.getComputedStyle(el).backgroundImage || '';
  const match = bg.match(/url\\(["']?([^"')]+)["']?\\)/i);
  if (match) values.push(match[1]);
}
return values.filter(src => new RegExp('^(https?:)?//', 'i').test(src));
"""
        )
    except Exception:
        return []
    result = []
    seen = set()
    for value in values:
        text = str(value or "")
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _remote_image_sources(browser) -> set[str]:
    return set(_remote_image_sources_ordered(browser))


def _short_url(value: str) -> str:
    text = str(value or "")
    return text if len(text) <= 180 else text[:177] + "..."


def _normalize_xiumi_image_url(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("//"):
        return "https:" + text
    return text


def _looks_like_user_xiumi_image(value: str) -> bool:
    text = str(value or "").lower()
    if not text:
        return False
    if "statics.xiumi.us" in text or "/stc/" in text or "templates-assets" in text:
        return False
    return "img.xiumi.us" in text or "/xmi/ua/" in text


def _file_input_count(browser) -> int:
    try:
        return len(browser.find_elements(By.CSS_SELECTOR, "input[type='file']"))
    except Exception:
        return 0


def _file_input_diagnostics(browser) -> list[dict]:
    script = """
return Array.from(document.querySelectorAll('input[type="file"]')).map((el, index) => {
  const style = window.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  const parent = el.parentElement;
  return {
    index,
    accept: el.getAttribute('accept') || '',
    multiple: !!el.multiple,
    disabled: !!el.disabled,
    visible: style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0,
    width: Math.round(rect.width),
    height: Math.round(rect.height),
    id: el.id || '',
    name: el.name || '',
    className: String(el.className || ''),
    parentClass: parent ? String(parent.className || '') : '',
    parentText: parent ? String(parent.innerText || '').replace(/\\s+/g, ' ').slice(0, 80) : ''
  };
});
"""
    try:
        values = browser.execute_script(script) or []
    except Exception:
        return []
    diagnostics = [value for value in values if isinstance(value, dict)]
    _log_xiumi_debug("file_input_diagnostics", inputs=diagnostics)
    return diagnostics


def _click_xiumi_ui_candidates(browser, include_terms: list[str], *, exclude_terms: list[str] | None = None, limit: int = 1) -> dict:
    script = """
const includeTerms = arguments[0].map(t => String(t).toLowerCase());
const excludeTerms = arguments[1].map(t => String(t).toLowerCase());
const limit = arguments[2];
function visible(el) {
  const style = window.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  return style && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
}
function haystack(el) {
  return [
    el.innerText, el.textContent, el.title, el.alt, el.getAttribute('aria-label'),
    el.id, el.className, el.getAttribute('data-title'), el.getAttribute('data-name')
  ].join(' ').toLowerCase();
}
const selector = [
  'button', 'a', 'label', 'li', 'span', 'i', 'em',
  '[role="button"]', '[title]', '[aria-label]', '[class*="image"]',
  '[class*="img"]', '[class*="pic"]', '[class*="upload"]'
].join(',');
const candidates = Array.from(document.querySelectorAll(selector))
  .filter(el => visible(el))
  .map(el => {
    const text = haystack(el);
    let score = 0;
    let matched = false;
    for (const term of includeTerms) {
      if (!term) continue;
      if (text === term) {
        score += 20;
        matched = true;
      } else if (text.includes(term)) {
        score += 8;
        matched = true;
      }
    }
    if (!matched) return { el, score: -999, text };
    for (const term of excludeTerms) {
      if (term && text.includes(term)) score -= 30;
    }
    const tag = el.tagName.toLowerCase();
    if (tag === 'button' || tag === 'label' || el.getAttribute('role') === 'button') score += 3;
    return { el, score, text };
  })
  .filter(item => item.score > 0)
  .sort((a, b) => b.score - a.score);
const clickedItems = [];
for (const item of candidates.slice(0, limit)) {
  try {
    item.el.scrollIntoView({ block: 'center', inline: 'center' });
    item.el.click();
    clickedItems.push({ score: item.score, text: item.text.slice(0, 160) });
  } catch (e) {}
}
return { clicked: clickedItems.length, candidates: candidates.length, items: clickedItems };
"""
    try:
        value = browser.execute_script(script, include_terms, exclude_terms or [], limit) or {}
        if isinstance(value, dict):
            return value
        return {"clicked": int(value or 0), "candidates": 0, "items": []}
    except Exception:
        return {"clicked": 0, "candidates": 0, "items": []}


def _open_xiumi_image_library(browser) -> dict:
    state = {"gallery": 0, "upload_button": 0, "file_inputs_before": _file_input_count(browser)}

    exclude = ["保存", "预览", "导出", "关闭", "删除", "推送", "上传推送", "打开", "save", "preview", "export", "close", "delete"]
    steps = [
        ("gallery", ["我的图库", "图库", "图片库"], exclude),
        ("upload_button", ["上传图片", "无水印", "图片上传"], exclude),
    ]
    for key, terms, blocked in steps:
        click_state = _click_xiumi_ui_candidates(browser, terms, exclude_terms=blocked, limit=1)
        clicked = int(click_state.get("clicked", 0) or 0)
        state[key] = state.get(key, 0) + clicked
        _log_xiumi_debug(
            "xiumi_ui_click_step",
            step=key,
            terms=terms,
            click_state=click_state,
            file_inputs=_file_input_count(browser),
        )
        if clicked:
            time.sleep(0.8)
    state["file_inputs_after"] = _file_input_count(browser)
    _log_xiumi_debug("xiumi_library_open_state", **state)
    return state


def _find_image_file_input(browser):
    library_state = _open_xiumi_image_library(browser)
    inputs = browser.find_elements(By.CSS_SELECTOR, "input[type='file']")
    diagnostics = _file_input_diagnostics(browser)
    input_meta = {int(item.get("index", -1)): item for item in diagnostics}

    ranked = []
    for index, element in enumerate(inputs):
        meta = input_meta.get(index, {})
        accept = str(meta.get("accept", ""))
        text = " ".join(
            str(meta.get(key, ""))
            for key in ("id", "name", "className", "parentClass", "parentText")
        ).lower()
        is_image_input = bool(re.search(r"(?:image|\.png|\.jpe?g|\.gif)", accept, flags=re.I))
        if not is_image_input:
            continue

        score = index
        input_id = str(meta.get("id", ""))
        score += 100
        if input_id == "imageFileUploadInput":
            score += 80
        if input_id == "teamImageFileUploadInput":
            score -= 60
        if not meta.get("disabled"):
            score += 20
        if meta.get("visible"):
            score += 40
        if meta.get("multiple"):
            score += 15
        if "无水印" in str(meta.get("parentText", "")):
            score += 40
        if any(term in text for term in ("上传", "图片", "图库", "image", "img", "pic", "upload", "gallery")):
            score += 30
        if any(term in text for term in ("team", "团队", "cover", "封面", "video", "audio", "file-attachment", "附件")):
            score -= 80
        ranked.append((score, index, element, meta))

    ranked.sort(key=lambda item: item[0], reverse=True)
    chosen = ranked[0] if ranked else None
    if chosen:
        score, index, element, meta = chosen
        _log_xiumi_debug("file_input_selected", index=index, score=score, total=len(inputs), meta=meta)
        return element, len(inputs), library_state
    _log_xiumi_debug("file_input_missing", total=0, library_state=library_state)
    return None, len(inputs), library_state


def _prepare_file_input_for_upload(browser, file_input):
    try:
        state = _file_input_state(browser, file_input)
        if state.get("visible") and int(state.get("width") or 0) > 0 and int(state.get("height") or 0) > 0:
            _log_xiumi_debug("file_input_prepare_skipped", reason="already_visible", state=state)
            return
        browser.execute_script(
            """
const el = arguments[0];
let current = el;
for (let depth = 0; current && depth < 5; depth += 1, current = current.parentElement) {
  current.removeAttribute('hidden');
  current.classList.remove('ng-hide', 'hide', 'hidden');
  current.style.display = 'block';
  current.style.visibility = 'visible';
  current.style.opacity = 1;
}
el.removeAttribute('disabled');
el.style.position = 'fixed';
el.style.left = '8px';
el.style.top = '8px';
el.style.width = '240px';
el.style.height = '32px';
el.style.zIndex = 2147483647;
""",
            file_input,
        )
        _log_xiumi_debug("file_input_prepared", state_before=state, state_after=_file_input_state(browser, file_input))
    except Exception:
        pass


def _activate_file_upload_control(browser, file_input) -> dict:
    script = """
const el = arguments[0];
const control =
  el.closest('label,button,a,[role="button"],.btn,.btn-upload,.tn-image-uploader') ||
  el.parentElement;
if (!control) return { clicked: false, reason: 'parent_missing' };
const text = String(control.innerText || control.textContent || '').replace(/\\s+/g, ' ').trim();
try {
  control.scrollIntoView({ block: 'center', inline: 'center' });
  control.click();
  return { clicked: true, text, tag: control.tagName, className: String(control.className || '') };
} catch (e) {
  return { clicked: false, text, error: String(e) };
}
"""
    try:
        state = browser.execute_script(script, file_input) or {}
    except Exception as exc:
        state = {"clicked": False, "error": str(exc)}
    _log_xiumi_debug("upload_control_activate", state=state)
    return state


def _file_input_cdp_selector(browser, file_input) -> str:
    try:
        state = _file_input_state(browser, file_input)
        input_id = str(state.get("id", "") or "").strip()
        if input_id:
            return f"#{input_id}"
        index = browser.execute_script(
            """
const target = arguments[0];
return Array.from(document.querySelectorAll('input[type="file"]')).indexOf(target);
""",
            file_input,
        )
        if isinstance(index, int) and index >= 0:
            return f'input[type="file"]:nth-of-type({index + 1})'
    except Exception:
        pass
    return ""


def _attach_files_with_cdp(browser, file_input, image_paths: list[pathlib.Path]) -> dict:
    if not hasattr(browser, "execute_cdp_cmd"):
        return {"applied": False, "reason": "cdp_unavailable"}
    selector = _file_input_cdp_selector(browser, file_input)
    if not selector:
        return {"applied": False, "reason": "selector_unavailable"}
    try:
        root = browser.execute_cdp_cmd("DOM.getDocument", {})
        node = browser.execute_cdp_cmd(
            "DOM.querySelector",
            {"nodeId": root["root"]["nodeId"], "selector": selector},
        )
        node_id = node.get("nodeId")
        if not node_id:
            return {"applied": False, "selector": selector, "reason": "node_not_found"}
        browser.execute_cdp_cmd(
            "DOM.setFileInputFiles",
            {"nodeId": node_id, "files": [str(path) for path in image_paths]},
        )
        return {"applied": True, "selector": selector}
    except Exception as exc:
        return {"applied": False, "selector": selector, "reason": str(exc)}


def _attach_file_with_cdp(browser, file_input, image_path: pathlib.Path) -> dict:
    return _attach_files_with_cdp(browser, file_input, [image_path])


def _attach_file_to_input(browser, file_input, image_path: pathlib.Path) -> tuple[dict, dict]:
    before_state = _file_input_state(browser, file_input)
    _activate_file_upload_control(browser, file_input)
    try:
        file_input.send_keys(str(image_path))
    except Exception as exc:
        _log_xiumi_debug("send_keys_exception", image=image_path.name, error=str(exc), state=before_state)

    after_send_keys_state = _file_input_state(browser, file_input)
    if int(after_send_keys_state.get("filesLength") or 0) < 1:
        cdp_state = _attach_file_with_cdp(browser, file_input, image_path)
        _log_xiumi_debug("cdp_file_attach", image=image_path.name, state=cdp_state)
        after_send_keys_state = _file_input_state(browser, file_input)

    _dispatch_file_input_events(browser, file_input)
    after_dispatch_state = _file_input_state(browser, file_input)
    return after_send_keys_state, after_dispatch_state


def _attach_files_to_input(browser, file_input, image_paths: list[pathlib.Path]) -> tuple[dict, dict]:
    before_state = _file_input_state(browser, file_input)
    _activate_file_upload_control(browser, file_input)
    joined_paths = "\n".join(str(path) for path in image_paths)
    try:
        file_input.send_keys(joined_paths)
    except Exception as exc:
        _log_xiumi_debug(
            "batch_send_keys_exception",
            images=[path.name for path in image_paths],
            error=str(exc),
            state=before_state,
        )

    after_send_keys_state = _file_input_state(browser, file_input)
    expected = len(image_paths)
    if int(after_send_keys_state.get("filesLength") or 0) < expected:
        cdp_state = _attach_files_with_cdp(browser, file_input, image_paths)
        _log_xiumi_debug("batch_cdp_file_attach", images=[path.name for path in image_paths], state=cdp_state)
        after_send_keys_state = _file_input_state(browser, file_input)

    _dispatch_file_input_events(browser, file_input)
    after_dispatch_state = _file_input_state(browser, file_input)
    return after_send_keys_state, after_dispatch_state


def _file_input_state(browser, file_input) -> dict:
    script = """
const el = arguments[0];
const style = window.getComputedStyle(el);
const rect = el.getBoundingClientRect();
return {
  value: el.value || '',
  filesLength: el.files ? el.files.length : null,
  accept: el.getAttribute('accept') || '',
  multiple: !!el.multiple,
  disabled: !!el.disabled,
  visible: style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0,
  width: Math.round(rect.width),
  height: Math.round(rect.height),
  id: el.id || '',
  className: String(el.className || '')
};
"""
    try:
        return browser.execute_script(script, file_input) or {}
    except Exception as exc:
        return {"error": str(exc)}


def _dispatch_file_input_events(browser, file_input):
    script = """
const el = arguments[0];
for (const name of ['input', 'change']) {
  try {
    el.dispatchEvent(new Event(name, { bubbles: true }));
  } catch (e) {}
}
if (window.angular) {
  try {
    const scope = window.angular.element(el).scope();
    if (scope && scope.$applyAsync) scope.$applyAsync();
    else if (scope && scope.$apply) scope.$apply();
  } catch (e) {}
}
"""
    try:
        browser.execute_script(script, file_input)
    except Exception:
        pass


def _xiumi_visible_messages(browser) -> list[str]:
    script = """
const parts = [];
for (const el of Array.from(document.querySelectorAll('body, .toast, .toast-message, .alert, .modal, .tips, [class*="toast"], [class*="alert"], [class*="message"], [class*="error"]'))) {
  const style = window.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  if (!style || style.display === 'none' || style.visibility === 'hidden' || rect.width <= 0 || rect.height <= 0) continue;
  const text = String(el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
  if (text && /上传|失败|错误|cos|COS|图片|图库/.test(text)) parts.push(text.slice(0, 500));
}
return Array.from(new Set(parts)).slice(0, 8);
"""
    try:
        values = browser.execute_script(script) or []
    except Exception:
        return []
    return [str(value) for value in values if value]


def _write_probe_image(temp_dir: pathlib.Path) -> pathlib.Path:
    data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAEAAAAAwCAIAAABOyVRHAAAAPElEQVR4nO3PQQ0AIBDAMMC/5+ONAvZoFSzZnYFn"
        "NzMAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADg1wGfXgAB3WQj8QAAAABJRU5ErkJggg=="
    )
    path = temp_dir / "wanyou_xiumi_upload_probe.png"
    path.write_bytes(data)
    return path


def _probe_xiumi_image_upload(browser, timeout: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="wanyou_xiumi_probe_") as temp:
        image_path = _write_probe_image(pathlib.Path(temp))
        print("秀米：正在检查图片上传链路")
        remote_url = _upload_one_xiumi_image(browser, image_path, timeout)
    status = "ok" if remote_url else "failed"
    _log_xiumi_debug("upload_probe", status=status, remote_url=_short_url(remote_url))
    return {"status": status, "remote_url": remote_url}


def _upload_one_xiumi_image(browser, image_path: pathlib.Path, timeout: int) -> str:
    file_input, input_count, library_state = _find_image_file_input(browser)
    if file_input is None:
        _log_xiumi_debug("upload_unavailable", image=image_path.name, input_count=input_count, library_state=library_state)
        return ""

    # Open the library first, then take the baseline. Otherwise existing gallery
    # and template thumbnails are misidentified as images uploaded by this run.
    before = _remote_image_sources(browser)
    _log_xiumi_debug(
        "upload_start",
        image=image_path.name,
        before_remote_count=len(before),
    )

    try:
        _prepare_file_input_for_upload(browser, file_input)
        before_dispatch_state, after_dispatch_state = _attach_file_to_input(browser, file_input, image_path)
        _log_xiumi_debug(
            "send_keys_done",
            image=image_path.name,
            path=str(image_path),
            before_dispatch_state=before_dispatch_state,
            after_dispatch_state=after_dispatch_state,
        )
        if int(after_dispatch_state.get("filesLength") or 0) < 1:
            _log_xiumi_debug(
                "file_input_empty_after_dispatch",
                image=image_path.name,
                before_dispatch_state=before_dispatch_state,
                after_dispatch_state=after_dispatch_state,
                note="Xiumi may clear file inputs immediately after processing starts.",
            )
    except Exception as exc:
        _log_xiumi_debug("send_keys_failed", image=image_path.name, error=str(exc))
        return ""

    first_timeout = int(getattr(config, "XIUMI_FIRST_IMAGE_UPLOAD_WAIT_SECONDS", 0) or 0)
    effective_timeout = max(5, first_timeout or timeout)
    deadline = time.time() + effective_timeout
    logged_source_sets = set()
    while time.time() < deadline:
        after = _remote_image_sources(browser)
        new_sources = [src for src in after - before if src and not src.startswith("data:")]
        user_sources = [src for src in new_sources if _looks_like_user_xiumi_image(src)]
        source_key = (len(new_sources), len(user_sources), tuple(sorted(new_sources[:3])))
        if new_sources and source_key not in logged_source_sets:
            logged_source_sets.add(source_key)
            _log_xiumi_debug(
                "gallery_new_sources",
                image=image_path.name,
                count=len(new_sources),
                user_count=len(user_sources),
                samples=[_short_url(src) for src in new_sources[:5]],
            )
        if user_sources:
            return _normalize_xiumi_image_url(user_sources[-1])
        time.sleep(0.5)
    visible_messages = _xiumi_visible_messages(browser)
    _log_xiumi_debug(
        "upload_timeout",
        image=image_path.name,
        gallery_new_sources=len(_remote_image_sources(browser) - before),
        user_gallery_sources=len([src for src in _remote_image_sources(browser) - before if _looks_like_user_xiumi_image(src)]),
        visible_messages=visible_messages,
        timeout=timeout,
        effective_timeout=effective_timeout,
    )
    return ""


def _upload_xiumi_image_batch(browser, image_paths: list[pathlib.Path], timeout: int) -> list[str]:
    if not image_paths:
        return []
    if len(image_paths) == 1:
        remote_url = _upload_one_xiumi_image(browser, image_paths[0], timeout)
        return [remote_url] if remote_url else []

    file_input, input_count, library_state = _find_image_file_input(browser)
    if file_input is None:
        _log_xiumi_debug(
            "batch_upload_unavailable",
            images=[path.name for path in image_paths],
            input_count=input_count,
            library_state=library_state,
        )
        return []

    before = set(_remote_image_sources_ordered(browser))
    _log_xiumi_debug(
        "batch_upload_start",
        images=[path.name for path in image_paths],
        before_remote_count=len(before),
    )

    try:
        _prepare_file_input_for_upload(browser, file_input)
        before_dispatch_state, after_dispatch_state = _attach_files_to_input(browser, file_input, image_paths)
        _log_xiumi_debug(
            "batch_send_keys_done",
            images=[path.name for path in image_paths],
            paths=[str(path) for path in image_paths],
            before_dispatch_state=before_dispatch_state,
            after_dispatch_state=after_dispatch_state,
        )
        if int(after_dispatch_state.get("filesLength") or 0) < 1:
            _log_xiumi_debug(
                "batch_file_input_empty_after_dispatch",
                images=[path.name for path in image_paths],
                before_dispatch_state=before_dispatch_state,
                after_dispatch_state=after_dispatch_state,
                note="Xiumi may clear file inputs immediately after processing starts.",
            )
    except Exception as exc:
        _log_xiumi_debug("batch_send_keys_failed", images=[path.name for path in image_paths], error=str(exc))
        return []

    first_timeout = int(getattr(config, "XIUMI_FIRST_IMAGE_UPLOAD_WAIT_SECONDS", 0) or 0)
    effective_timeout = max(10, first_timeout, timeout * len(image_paths))
    effective_timeout = min(effective_timeout, 180)
    deadline = time.time() + effective_timeout
    logged_counts = set()
    while time.time() < deadline:
        after_ordered = _remote_image_sources_ordered(browser)
        new_sources = [src for src in after_ordered if src and src not in before and not src.startswith("data:")]
        user_sources = [_normalize_xiumi_image_url(src) for src in new_sources if _looks_like_user_xiumi_image(src)]
        count_key = (len(new_sources), len(user_sources))
        if user_sources and count_key not in logged_counts:
            logged_counts.add(count_key)
            _log_xiumi_debug(
                "batch_gallery_new_sources",
                images=[path.name for path in image_paths],
                count=len(new_sources),
                user_count=len(user_sources),
                samples=[_short_url(src) for src in user_sources[:8]],
            )
        if len(user_sources) >= len(image_paths):
            return user_sources[-len(image_paths):]
        time.sleep(0.5)

    visible_messages = _xiumi_visible_messages(browser)
    after = set(_remote_image_sources_ordered(browser))
    user_sources = [_normalize_xiumi_image_url(src) for src in after - before if _looks_like_user_xiumi_image(src)]
    _log_xiumi_debug(
        "batch_upload_timeout",
        images=[path.name for path in image_paths],
        gallery_new_sources=len(after - before),
        user_gallery_sources=len(user_sources),
        visible_messages=visible_messages,
        timeout=timeout,
        effective_timeout=effective_timeout,
    )
    return user_sources


def _chunks(values: list, size: int):
    for index in range(0, len(values), max(1, size)):
        yield values[index:index + max(1, size)]


def _upload_xiumi_images_and_rewrite(browser, html_text: str, asset_base_path: pathlib.Path, timeout: int) -> tuple[str, dict]:
    mode = str(getattr(config, "XIUMI_IMAGE_MODE", "upload") or "upload").strip().lower()
    if mode != "upload":
        return html_text, {"status": "skipped", "uploaded": 0, "total": 0}

    with tempfile.TemporaryDirectory(prefix="wanyou_xiumi_images_") as temp:
        temp_dir = pathlib.Path(temp)
        images = _image_sources_for_upload(html_text, asset_base_path, temp_dir)
        _log_xiumi_debug("upload_candidates", total=len(images), images=[path.name for _source, path in images])
        if not images:
            return html_text, {"status": "no_images", "uploaded": 0, "total": 0}

        rewritten = html_text
        uploaded = 0
        failures = 0
        consecutive_failures = 0
        skipped_images = []
        max_failures = max(1, int(getattr(config, "XIUMI_IMAGE_UPLOAD_MAX_FAILURES", 3) or 3))
        retries = max(0, int(getattr(config, "XIUMI_IMAGE_UPLOAD_RETRIES", 1) or 0))
        batch_size = max(1, int(getattr(config, "XIUMI_IMAGE_UPLOAD_BATCH_SIZE", 6) or 1))

        def upload_single(source: str, image_path: pathlib.Path) -> str:
            remote_url = ""
            for attempt in range(retries + 1):
                remote_url = _upload_one_xiumi_image(browser, image_path, timeout)
                if remote_url:
                    break
                if attempt < retries:
                    _log_xiumi_debug("upload_retry", image=image_path.name, attempt=attempt + 1, retries=retries)
                    time.sleep(1)
            return remote_url

        for batch in _chunks(images, batch_size):
            batch_urls = []
            if len(batch) > 1:
                batch_urls = _upload_xiumi_image_batch(browser, [image_path for _source, image_path in batch], timeout)
                if len(batch_urls) == len(batch):
                    _log_xiumi_debug(
                        "batch_upload_success",
                        images=[path.name for _source, path in batch],
                        uploaded=len(batch_urls),
                    )
                else:
                    _log_xiumi_debug(
                        "batch_upload_incomplete",
                        images=[path.name for _source, path in batch],
                        received=len(batch_urls),
                        expected=len(batch),
                    )
                    batch_urls = []

            if batch_urls:
                for (source, image_path), remote_url in zip(batch, batch_urls):
                    rewritten = rewritten.replace(source, remote_url)
                    uploaded += 1
                    consecutive_failures = 0
                    _log_xiumi_debug("upload_success", image=image_path.name, remote_url=_short_url(remote_url), uploaded=uploaded, mode="batch")
                continue

            for source, image_path in batch:
                remote_url = upload_single(source, image_path)
                if remote_url:
                    rewritten = rewritten.replace(source, remote_url)
                    uploaded += 1
                    consecutive_failures = 0
                    _log_xiumi_debug("upload_success", image=image_path.name, remote_url=_short_url(remote_url), uploaded=uploaded, mode="single")
                    continue

                failures += 1
                consecutive_failures += 1
                skipped_images.append(image_path.name)
                _log_xiumi_debug(
                    "upload_failure",
                    image=image_path.name,
                    failures=failures,
                    consecutive_failures=consecutive_failures,
                    max_failures=max_failures,
                    uploaded=uploaded,
                )
                if uploaded == 0 and consecutive_failures >= max_failures:
                    _log_xiumi_debug(
                        "upload_abort",
                        reason="initial_consecutive_failures",
                        failures=failures,
                        consecutive_failures=consecutive_failures,
                        uploaded=uploaded,
                        total=len(images),
                    )
                    break
            if uploaded == 0 and consecutive_failures >= max_failures:
                break

        status = "ok" if uploaded == len(images) else "partial" if uploaded else "failed"
        if status == "ok":
            print(f"秀米：正文图片已上传完成（{uploaded}/{len(images)}）")
        elif uploaded:
            print(f"秀米：部分正文图片已上传（{uploaded}/{len(images)}），未上传图片将保留提示")
        else:
            print("秀米：正文图片未能自动上传，将在草稿中保留提示")
        _log_xiumi_debug(
            "upload_summary",
            status=status,
            uploaded=uploaded,
            failed=failures,
            skipped_images=skipped_images,
            total=len(images),
        )
        if uploaded:
            return _remove_unuploaded_images_for_xiumi(rewritten), {"status": status, "uploaded": uploaded, "total": len(images)}
        return _remove_images_for_xiumi(html_text), {"status": status, "uploaded": 0, "total": len(images)}


def _mark_xiumi_document_dirty(browser) -> dict:
    return browser.execute_script(
        """
function findSaveScope() {
  var btn = document.querySelector('button.btn-img.op-btn.save');
  if (!btn || !window.angular) return null;
  var s = window.angular.element(btn).scope();
  while (s && typeof s.onBtnClickSave !== 'function') s = s.$parent;
  return s || null;
}
var scope = findSaveScope();
var out = { applied: false, dirty: null, canUndo: null, empty: null };
if (!scope) return out;
try {
  if (scope.$apply) {
    scope.$apply(function () {
      if (scope.undoStatus) {
        scope.undoStatus.isDirty = true;
        scope.undoStatus.canUndo = true;
      }
      if (scope.status && scope.status.show) {
        scope.status.show.empty = false;
      }
    });
  } else {
    if (scope.undoStatus) {
      scope.undoStatus.isDirty = true;
      scope.undoStatus.canUndo = true;
    }
    if (scope.status && scope.status.show) {
      scope.status.show.empty = false;
    }
  }
  out.applied = true;
} catch (e) {
  out.error = String(e);
}
out.dirty = scope.undoStatus ? scope.undoStatus.isDirty : null;
out.canUndo = scope.undoStatus ? scope.undoStatus.canUndo : null;
out.empty = scope.status && scope.status.show ? scope.status.show.empty : null;
return out;
""",
    ) or {}


def _click_save(browser):
    save_button = browser.find_element(By.CSS_SELECTOR, "button.btn-img.op-btn.save")
    browser.execute_script("arguments[0].click();", save_button)


def _wait_for_save_result(browser, old_url: str, timeout: int) -> tuple[str, str]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        current_url = browser.current_url
        if "/for/new/" not in current_url:
            return "url_changed", current_url
        if current_url != old_url and "/for/new/" not in current_url:
            return "url_changed", current_url
        if _visible_login_links(browser):
            return "login_required", current_url
        time.sleep(1)
    return "timeout", browser.current_url


def _save_diagnostics(browser) -> dict:
    try:
        body_text = browser.execute_script("return document.body ? document.body.innerText : '';") or ""
    except Exception:
        body_text = ""
    body_text = re.sub(r"\s+", " ", str(body_text)).strip()
    return {
        "url": browser.current_url,
        "login_links": len(_visible_login_links(browser)),
        "save_buttons": len(browser.find_elements(By.CSS_SELECTOR, "button.btn-img.op-btn.save")),
        "editable": len(browser.find_elements(By.XPATH, '//*[@contenteditable="true"]')),
        "body_excerpt": body_text[:240],
    }


def _fill_xiumi_fields(browser, title: str, author: str, source_url: str, digest: str):
    _set_input_value(browser, "input.title", title)
    _set_input_value(browser, "input.author", author)
    if source_url:
        _set_input_value(browser, "input.link", source_url)
    if digest:
        _set_input_value(browser, "textarea.desc", digest)


def _fill_xiumi_body_then_images(browser, content_html: str, asset_base_path: pathlib.Path, *, upload_probe: bool = False) -> tuple[dict, bool]:
    print("秀米：正在写入正文文字")
    text_first_html = _replace_images_with_placeholders_for_xiumi(content_html)
    model_applied = _set_editor_html(browser, text_first_html)
    _log_xiumi_debug("xiumi_body_text_model_applied", applied=bool(model_applied))

    upload_state = {"status": "skipped", "uploaded": 0, "total": 0}
    mode = str(getattr(config, "XIUMI_IMAGE_MODE", "upload") or "upload").strip().lower()
    if mode == "upload":
        if upload_probe:
            probe_state = _probe_xiumi_image_upload(
                browser,
                max(5, getattr(config, "XIUMI_FIRST_IMAGE_UPLOAD_WAIT_SECONDS", 20)),
            )
            if probe_state.get("status") != "ok":
                print("秀米：测试图片上传失败，跳过正文图片上传。")
                upload_state = {"status": "probe_failed", "uploaded": 0, "total": _image_payload_stats(content_html)["image_count"]}
                final_html = _remove_images_for_xiumi(content_html)
                model_applied = _set_editor_html(browser, final_html)
                dirty_state = _mark_xiumi_document_dirty(browser)
                _log_xiumi_debug("xiumi_body_image_model_applied", applied=bool(model_applied))
                _log_xiumi_debug("xiumi_dirty_state", **dirty_state)
                return upload_state, model_applied

        print("秀米：正在上传正文图片")
        final_html, upload_state = _upload_xiumi_images_and_rewrite(
            browser,
            content_html,
            asset_base_path,
            max(5, getattr(config, "XIUMI_IMAGE_UPLOAD_WAIT_SECONDS", 8)),
        )
        _log_xiumi_debug("xiumi_image_upload_state", **upload_state)
        print("秀米：正在应用最终排版")
        model_applied = _set_editor_html(browser, final_html)
        _log_xiumi_debug("xiumi_body_image_model_applied", applied=bool(model_applied))

    dirty_state = _mark_xiumi_document_dirty(browser)
    _log_xiumi_debug("xiumi_dirty_state", **dirty_state)
    return upload_state, model_applied


def publish_xiumi_draft(
    html_path: str,
    *,
    markdown: str = "",
    title: str = "",
    author: str = "物理系学生会",
    digest: str = "",
    source_url: str = "",
    profile_dir: str = "",
    home_url: str = "",
    editor_url: str = "",
    save_timeout: int = 0,
    login_timeout: int = 0,
    dry_run: bool = False,
    leave_open: bool = False,
    upload_probe: bool = False,
) -> dict:
    html_path_obj = pathlib.Path(html_path).resolve()
    if not html_path_obj.exists():
        raise FileNotFoundError(f"HTML 文件不存在: {html_path_obj}")

    content_html, asset_base_path = _resolve_content_paths(html_path_obj, markdown)
    content_html = _prepare_xiumi_images(content_html, asset_base_path)

    markdown_path = pathlib.Path(markdown).resolve() if markdown else html_path_obj.with_suffix(".md")
    markdown_text = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
    final_title = (title or _first_heading(markdown_text) or "万有预报").strip()
    final_digest = (digest or _first_summary_line(markdown_text) or "").strip()
    final_author = (author or "").strip()
    final_source_url = (source_url or "").strip()

    explicit_profile_dir = bool((profile_dir or "").strip())
    profile_dir_value = profile_dir or getattr(config, "XIUMI_PROFILE_DIR", "./output/selenium_cache/xiumi-profile")
    profile_dir_path = pathlib.Path(profile_dir_value).resolve()
    home_url_value = home_url or editor_url or getattr(config, "XIUMI_HOME_URL", "https://xiumi.us/studio/v5?lang=zh_CN#/")
    save_timeout_value = int(save_timeout or getattr(config, "XIUMI_SAVE_WAIT_SECONDS", 30))
    login_timeout_value = int(login_timeout or getattr(config, "XIUMI_LOGIN_WAIT_SECONDS", 600))

    _log_xiumi_debug("xiumi_profile_dir", path=str(profile_dir_path))
    browser = _make_xiumi_browser(profile_dir_path)
    result = {
        "status": "unknown",
        "editor_url": "",
        "draft_url": "",
        "title": final_title,
        "profile_dir": str(profile_dir_path),
    }
    keep_browser_open = False
    try:
        print("秀米：正在打开图文编辑器")
        _open_xiumi_editor(
            browser,
            home_url_value,
            login_timeout_value,
            max(15, getattr(config, "WAIT_TIMEOUT", 15)),
        )

        print("秀米：正在填充标题、作者和摘要")
        _fill_xiumi_fields(browser, final_title, final_author, final_source_url, final_digest)
        _fill_xiumi_body_then_images(browser, content_html, asset_base_path, upload_probe=upload_probe)

        result["editor_url"] = browser.current_url

        if dry_run:
            print("秀米：已完成自动填充，未点击保存")
            print(f"秀米编辑器地址：{browser.current_url}")
            result["status"] = "dry_run"
        else:
            print("秀米：正在点击保存")
            before_url = browser.current_url
            _click_save(browser)
            save_state, current_url = _wait_for_save_result(browser, before_url, save_timeout_value)
            if save_state == "login_required":
                print("秀米：保存前需要重新登录")
                logged_in = _wait_for_manual_login(browser, login_timeout_value)
                if not logged_in:
                    raise RuntimeError("秀米保存前登录未完成，已超过等待时间。")
                _open_xiumi_editor(
                    browser,
                    home_url_value,
                    login_timeout_value,
                    max(15, getattr(config, "WAIT_TIMEOUT", 15)),
                )
                _wait_editor_ready(browser, max(15, getattr(config, "WAIT_TIMEOUT", 15)))
                _fill_xiumi_fields(browser, final_title, final_author, final_source_url, final_digest)
                _fill_xiumi_body_then_images(browser, content_html, asset_base_path, upload_probe=upload_probe)
                before_url = browser.current_url
                print("秀米：登录完成，重新点击保存")
                _click_save(browser)
                save_state, current_url = _wait_for_save_result(browser, before_url, save_timeout_value)
            result["editor_url"] = current_url
            if save_state == "url_changed":
                print("秀米：草稿已保存")
                print(f"秀米草稿地址：{current_url}")
                result["status"] = "saved"
                result["draft_url"] = current_url
            else:
                diagnostics = _save_diagnostics(browser)
                _log_xiumi_debug("xiumi_save_diagnostics", diagnostics=diagnostics)
                print("秀米：保存状态未能自动确认，请在浏览器中检查是否已保存")
                print(f"秀米编辑器地址：{current_url}")
                result["status"] = "uncertain"

        _wait_for_user_before_closing_browser()
        return result
    except Exception as exc:
        keep_browser_open = True
        result["status"] = "error"
        result["editor_url"] = getattr(browser, "current_url", "")
        result["error"] = f"{type(exc).__name__}: {exc}"
        _log_xiumi_debug(
            "xiumi_exception",
            error=result["error"],
            traceback=traceback.format_exc(),
            url=result["editor_url"],
            excerpt=_page_excerpt(browser),
        )
        print(f"秀米：发生异常，浏览器将保留打开便于检查：{result['error']}")
        print("确认后回到命令行按回车结束程序。详细日志在 output/xiumi_debug。")
        _wait_for_user_before_closing_browser()
        return result
    finally:
        if keep_browser_open:
            _log_xiumi_debug("xiumi_browser_close", status="skipped_after_error")
        else:
            try:
                browser.quit()
            except Exception as exc:
                _log_xiumi_debug("xiumi_browser_close", status="ignored", error=str(exc))
        if (
            not keep_browser_open
            and not explicit_profile_dir
            and browser_supports_profile_dir(getattr(browser, "_wanyou_browser_name", ""))
        ):
            cleaned = _cleanup_profile_dir(profile_dir_path)
            if cleaned:
                _log_xiumi_debug("xiumi_profile_cleanup", status="removed", path=str(profile_dir_path))
            else:
                _log_xiumi_debug("xiumi_profile_cleanup", status="failed", path=str(profile_dir_path))


def main():
    _configure_console()

    parser = argparse.ArgumentParser(description="Open Xiumi paper editor, fill content, and save a draft.")
    parser.add_argument("html_path", help="Final Wanyou HTML path.")
    parser.add_argument("--markdown", default="", help="Optional Markdown path; preferred for building inline richtext.")
    parser.add_argument("--title", default="", help="Draft title to fill in Xiumi.")
    parser.add_argument("--author", default="物理系学生会", help="Author to fill in Xiumi.")
    parser.add_argument("--digest", default="", help="Digest/summary to fill in Xiumi.")
    parser.add_argument("--source-url", default="", help="Original link field to fill in Xiumi.")
    parser.add_argument(
        "--profile-dir",
        default="",
        help=(
            "Optional browser profile directory. By default the configured Xiumi profile is used and "
            "cleaned after the browser closes; explicit profile directories are preserved."
        ),
    )
    parser.add_argument("--home-url", default=getattr(config, "XIUMI_HOME_URL", "https://xiumi.us/studio/v5?lang=zh_CN#/"), help="Xiumi home/My Xiumi URL used before creating a new paper.")
    parser.add_argument("--editor-url", default="", help="Deprecated alias for --home-url; direct paper/for/new is no longer used before login.")
    parser.add_argument("--save-timeout", type=int, default=getattr(config, "XIUMI_SAVE_WAIT_SECONDS", 30))
    parser.add_argument("--login-timeout", type=int, default=getattr(config, "XIUMI_LOGIN_WAIT_SECONDS", 600))
    parser.add_argument("--dry-run", action="store_true", help="Open and fill editor, but do not click save.")
    parser.add_argument(
        "--upload-probe",
        action="store_true",
        help="Upload a generated harmless test image first; upload body images only if the probe succeeds.",
    )
    parser.add_argument(
        "--leave-open",
        action="store_true",
        help="Compatibility option. The browser now stays open for editing by default until you press Enter.",
    )
    args = parser.parse_args()

    publish_xiumi_draft(
        args.html_path,
        markdown=args.markdown,
        title=args.title,
        author=args.author,
        digest=args.digest,
        source_url=args.source_url,
        profile_dir=args.profile_dir,
        home_url=args.home_url or args.editor_url,
        save_timeout=args.save_timeout,
        login_timeout=args.login_timeout,
        dry_run=args.dry_run,
        leave_open=args.leave_open,
        upload_probe=args.upload_probe,
    )


if __name__ == "__main__":
    main()
