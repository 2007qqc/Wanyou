import argparse
import datetime as dt
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from generators.h5_generator import decorate_markdown_with_theme, export_h5
from wanyou.crawlers_hall import crawl_hall
from wanyou.crawlers_info import crawl_info
from wanyou.crawlers_lib import crawl_lib
from wanyou.crawlers_myhome import crawl_myhome
from wanyou.crawlers_physics import crawl_physics
from wanyou.filter_debug import configure_filter_debug, finalize_filter_debug
from wanyou.synthesizer import build_augmented_markdown
from wanyou.unified_auth import authenticate_shared_browser
from wanyou.utils_auth import prompt_credentials
from wanyou.wechat_pipeline import collect_wechat_items, write_sectioned_md_stream


PUBLIC_MODULES = {"lib", "hall", "physics", "wechat"}
LOGIN_MODULES = {"info", "myhome"}
ALL_MODULES = ["info", "myhome", "lib", "hall", "physics", "wechat"]


def _configure_console():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _make_run_dir(module: str) -> tuple[str, str]:
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    run_dir = os.path.join(config.OUTPUT_DIR, f"module_{module}_{timestamp}")
    images_dir = os.path.join(run_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(os.path.join(run_dir, "debug"), exist_ok=True)
    return run_dir, images_dir


def _write_outputs(run_dir: str, module: str, raw_text: str, synthesize: bool, export_html: bool):
    raw_path = os.path.join(run_dir, f"wanyou_{module}_raw.md")
    final_path = os.path.join(run_dir, f"wanyou_{module}.md")
    html_path = os.path.join(run_dir, f"wanyou_{module}.html")

    pathlib.Path(raw_path).write_text(raw_text, encoding="utf-8")
    final_text = build_augmented_markdown(raw_text, current_markdown_path=raw_path) if synthesize else raw_text
    final_text = decorate_markdown_with_theme(final_text, final_path)
    pathlib.Path(final_path).write_text(final_text, encoding="utf-8")

    if export_html:
        export_h5(final_path, html_path, title=f"万有预报-{module}")
    else:
        html_path = ""

    print(f"raw_markdown_path: {raw_path}")
    print(f"final_markdown_path: {final_path}")
    if html_path:
        print(f"html_path: {html_path}")


def _run_public_module(module: str, doc, images_dir: str):
    if module == "lib":
        crawl_lib(doc, images_dir)
    elif module == "hall":
        crawl_hall(doc, "", images_dir)
    elif module == "physics":
        crawl_physics(doc, images_dir)
    elif module == "wechat":
        days_limit = getattr(config, "WECHAT_MAIN_RECENT_DAYS", 7)
        items = collect_wechat_items(days_limit=days_limit)
        write_sectioned_md_stream(items, doc, include_content=False)
    else:
        raise ValueError(f"未知公开模块: {module}")


def _run_login_modules(modules: list[str], doc, images_dir: str):
    credentials = prompt_credentials()
    info_credentials = credentials.get("info", {})
    myhome_credentials = credentials.get("myhome", {})
    username = info_credentials.get("username") or myhome_credentials.get("username", "")
    password = info_credentials.get("password") or myhome_credentials.get("password", "")
    browser = authenticate_shared_browser(
        username,
        password,
        debug_dir=os.path.join(os.path.dirname(images_dir), "debug"),
        initial_url=config.URL_INFO,
        stage_label="统一身份认证",
    )
    try:
        if "info" in modules:
            crawl_info(doc, images_dir, username=username, password=password, browser=browser)
        if "myhome" in modules:
            crawl_myhome(doc, images_dir, username=username, password=password, browser=browser)
    finally:
        try:
            browser.quit()
        except Exception:
            pass


def main():
    _configure_console()
    parser = argparse.ArgumentParser(description="Run one or more Wanyou modules and export Markdown/HTML.")
    parser.add_argument(
        "modules",
        nargs="+",
        help="Modules to run: info myhome lib hall physics wechat all public login",
    )
    parser.add_argument("--raw-only", action="store_true", help="Only write raw markdown, skip LLM synthesis/theme.")
    parser.add_argument("--skip-html", action="store_true", help="Skip HTML export. Kept for compatibility; same as --md-only.")
    parser.add_argument("--md-only", action="store_true", help="Only generate raw/final Markdown, without richtext HTML.")
    parser.add_argument("--with-richtext", action="store_true", help="Generate Markdown and richtext HTML. This is the default unless --md-only/--skip-html is set.")
    args = parser.parse_args()

    requested = []
    for module in args.modules:
        key = module.lower()
        if key == "all":
            requested.extend(ALL_MODULES)
        elif key == "public":
            requested.extend(["lib", "hall", "physics", "wechat"])
        elif key == "login":
            requested.extend(["info", "myhome"])
        elif key in PUBLIC_MODULES or key in LOGIN_MODULES:
            requested.append(key)
        else:
            raise SystemExit(f"未知模块: {module}")

    modules = []
    for module in requested:
        if module not in modules:
            modules.append(module)

    run_dir, images_dir = _make_run_dir("_".join(modules))
    configure_filter_debug(os.path.join(run_dir, "debug"), reset=True)
    raw_parts = []

    class _Buffer:
        def write(self, text):
            raw_parts.append(text)

    doc = _Buffer()
    login_modules = [module for module in modules if module in LOGIN_MODULES]
    public_modules = [module for module in modules if module in PUBLIC_MODULES]

    if login_modules:
        _run_login_modules(login_modules, doc, images_dir)
    for module in public_modules:
        _run_public_module(module, doc, images_dir)

    raw_text = "".join(raw_parts).strip() + "\n"
    export_html = args.with_richtext or not (args.md_only or args.skip_html)
    _write_outputs(run_dir, "_".join(modules), raw_text, synthesize=not args.raw_only, export_html=export_html)
    summary_path = finalize_filter_debug()
    if summary_path:
        print(f"filter_debug_summary_path: {summary_path}")


if __name__ == "__main__":
    main()
