import argparse
import base64
import mimetypes
import os
import pathlib
import re
import shutil
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from generators.wechat_inline import markdown_to_wechat_inline_html
from wanyou.browser import browser_supports_profile_dir, get_selenium_browser_name, make_browser_options, make_webdriver


def _configure_console():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


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
        print(f"xiumi_source_markdown: {markdown_path}")
        return markdown_to_wechat_inline_html(markdown_text, markdown_path=str(markdown_path)), markdown_path

    html_text = html_path.read_text(encoding="utf-8")
    print(f"xiumi_source_html: {html_path}")
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


def _open_xiumi_editor(browser, editor_url: str, login_timeout: int, wait_timeout: int):
    browser.get(editor_url)
    WebDriverWait(browser, wait_timeout).until(lambda d: d.execute_script("return document.readyState") in ("interactive", "complete"))

    if _visible_login_links(browser):
        logged_in = _wait_for_manual_login(browser, login_timeout)
        if not logged_in:
            raise RuntimeError("秀米登录未完成，已超过等待时间。")
        browser.get(editor_url)

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


def publish_xiumi_draft(
    html_path: str,
    *,
    markdown: str = "",
    title: str = "",
    author: str = "物理系学生会",
    digest: str = "",
    source_url: str = "",
    profile_dir: str = "",
    editor_url: str = "",
    save_timeout: int = 0,
    login_timeout: int = 0,
    dry_run: bool = False,
    leave_open: bool = False,
) -> dict:
    html_path_obj = pathlib.Path(html_path).resolve()
    if not html_path_obj.exists():
        raise FileNotFoundError(f"HTML 文件不存在: {html_path_obj}")

    content_html, asset_base_path = _resolve_content_paths(html_path_obj, markdown)
    content_html = _inline_local_images(content_html, asset_base_path)

    markdown_path = pathlib.Path(markdown).resolve() if markdown else html_path_obj.with_suffix(".md")
    markdown_text = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
    final_title = (title or _first_heading(markdown_text) or "万有预报").strip()
    final_digest = (digest or _first_summary_line(markdown_text) or "").strip()
    final_author = (author or "").strip()
    final_source_url = (source_url or "").strip()

    explicit_profile_dir = bool((profile_dir or "").strip())
    profile_dir_value = profile_dir or getattr(config, "XIUMI_PROFILE_DIR", "./output/selenium_cache/xiumi-profile")
    profile_dir_path = pathlib.Path(profile_dir_value).resolve()
    editor_url_value = editor_url or getattr(config, "XIUMI_EDITOR_URL", "https://xiumi.us/studio/v5?lang=zh_CN#/paper/for/new")
    save_timeout_value = int(save_timeout or getattr(config, "XIUMI_SAVE_WAIT_SECONDS", 30))
    login_timeout_value = int(login_timeout or getattr(config, "XIUMI_LOGIN_WAIT_SECONDS", 600))

    print(f"xiumi_profile_dir: {profile_dir_path}")
    browser = _make_xiumi_browser(profile_dir_path)
    result = {
        "status": "unknown",
        "editor_url": "",
        "draft_url": "",
        "title": final_title,
        "profile_dir": str(profile_dir_path),
    }
    try:
        print("秀米：正在打开图文编辑器")
        _open_xiumi_editor(
            browser,
            editor_url_value,
            login_timeout_value,
            max(15, getattr(config, "WAIT_TIMEOUT", 15)),
        )

        print("秀米：正在填充标题、作者、摘要和正文")
        _set_input_value(browser, "input.title", final_title)
        _set_input_value(browser, "input.author", final_author)
        if final_source_url:
            _set_input_value(browser, "input.link", final_source_url)
        if final_digest:
            _set_input_value(browser, "textarea.desc", final_digest)
        model_applied = _set_editor_html(browser, content_html)
        print(f"xiumi_body_model_applied: {'yes' if model_applied else 'no'}")
        dirty_state = _mark_xiumi_document_dirty(browser)
        print(
            "xiumi_dirty_state: "
            f"applied={'yes' if dirty_state.get('applied') else 'no'}, "
            f"dirty={dirty_state.get('dirty')}, "
            f"canUndo={dirty_state.get('canUndo')}, "
            f"empty={dirty_state.get('empty')}"
        )

        result["editor_url"] = browser.current_url

        if dry_run:
            print("xiumi_dry_run: 已完成自动填充，未点击保存。")
            print(f"xiumi_editor_url: {browser.current_url}")
            result["status"] = "dry_run"
        else:
            print("秀米：正在点击保存")
            before_url = browser.current_url
            _click_save(browser)
            save_state, current_url = _wait_for_save_result(browser, before_url, save_timeout_value)
            if save_state == "login_required":
                print("xiumi_save_status: login_required")
                logged_in = _wait_for_manual_login(browser, login_timeout_value)
                if not logged_in:
                    raise RuntimeError("秀米保存前登录未完成，已超过等待时间。")
                browser.get(editor_url_value)
                _wait_editor_ready(browser, max(15, getattr(config, "WAIT_TIMEOUT", 15)))
                _set_input_value(browser, "input.title", final_title)
                _set_input_value(browser, "input.author", final_author)
                if final_source_url:
                    _set_input_value(browser, "input.link", final_source_url)
                if final_digest:
                    _set_input_value(browser, "textarea.desc", final_digest)
                _set_editor_html(browser, content_html)
                _mark_xiumi_document_dirty(browser)
                before_url = browser.current_url
                print("秀米：登录完成，重新点击保存")
                _click_save(browser)
                save_state, current_url = _wait_for_save_result(browser, before_url, save_timeout_value)
            result["editor_url"] = current_url
            if save_state == "url_changed":
                print("xiumi_save_status: url_changed")
                print("xiumi_hint: 地址已从 for/new 变为草稿地址，但这仍不等于服务器端内容一定已持久化，请重新打开草稿核对正文。")
                print(f"xiumi_draft_url: {current_url}")
                result["status"] = "url_changed"
                result["draft_url"] = current_url
            else:
                print("xiumi_save_status: uncertain")
                diagnostics = _save_diagnostics(browser)
                print(
                    "xiumi_save_diagnostics: "
                    f"login_links={diagnostics['login_links']}, "
                    f"save_buttons={diagnostics['save_buttons']}, "
                    f"editable={diagnostics['editable']}, "
                    f"url={diagnostics['url']}"
                )
                if diagnostics.get("body_excerpt"):
                    print(f"xiumi_page_excerpt: {diagnostics['body_excerpt']}")
                print("xiumi_hint: 保存按钮已点击，但未在等待时间内确认 URL 从 for/new 变为正式草稿地址，请在浏览器中检查是否已保存。")
                print(f"xiumi_editor_url: {current_url}")
                result["status"] = "uncertain"

        _wait_for_user_before_closing_browser()
        return result
    finally:
        try:
            browser.quit()
        except Exception as exc:
            print(f"xiumi_browser_close: ignored ({exc})")
        if not explicit_profile_dir and browser_supports_profile_dir(getattr(browser, "_wanyou_browser_name", "")):
            cleaned = _cleanup_profile_dir(profile_dir_path)
            if cleaned:
                print(f"xiumi_profile_cleanup: removed ({profile_dir_path})")
            else:
                print(f"xiumi_profile_cleanup: failed ({profile_dir_path})")


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
    parser.add_argument("--editor-url", default=getattr(config, "XIUMI_EDITOR_URL", "https://xiumi.us/studio/v5?lang=zh_CN#/paper/for/new"))
    parser.add_argument("--save-timeout", type=int, default=getattr(config, "XIUMI_SAVE_WAIT_SECONDS", 30))
    parser.add_argument("--login-timeout", type=int, default=getattr(config, "XIUMI_LOGIN_WAIT_SECONDS", 600))
    parser.add_argument("--dry-run", action="store_true", help="Open and fill editor, but do not click save.")
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
        editor_url=args.editor_url,
        save_timeout=args.save_timeout,
        login_timeout=args.login_timeout,
        dry_run=args.dry_run,
        leave_open=args.leave_open,
    )


if __name__ == "__main__":
    main()
