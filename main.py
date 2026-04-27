import datetime
import os
import re
import sys

import config
from generators.browser_agent import export_browser_agent_payload
from generators.h5_generator import decorate_markdown_with_theme, export_h5
from wanyou.crawlers_hall import crawl_hall
from wanyou.crawlers_info import crawl_info
from wanyou.crawlers_lib import crawl_lib
from wanyou.crawlers_myhome import crawl_myhome
from wanyou.crawlers_physics import crawl_physics
from wanyou.filter_debug import configure_filter_debug, finalize_filter_debug
from wanyou.raw_ranker import build_ranked_raw_markdown, build_selected_raw_markdown_from_ranked
from wanyou.synthesizer import build_augmented_markdown
from wanyou.unified_auth import authenticate_shared_browser
from wanyou.utils_auth import prompt_credentials
from wanyou.utils_html import clean_markdown_document_with_llm
from wanyou.wechat_pipeline import collect_wechat_items, write_sectioned_md_stream


REQUIRED_SECTIONS = [
    "教务通知",
    "家园网信息",
    "图书馆信息",
    "学生会信息",
    "青年科协信息",
    "学生社团信息",
    "物理系学术报告",
    "学生公益信息",
]

STAGE_SECTION_MAP = {
    "crawl_info": "教务通知",
    "crawl_myhome": "家园网信息",
}


def _placeholder_section(section_name: str) -> str:
    return f"# {section_name}\n\n## 占位卡片\n\n等待下次抓取结果。\n\n"


def _error_placeholder_section(section_name: str, error_text: str) -> str:
    return (
        f"# {section_name}\n\n"
        "## 占位卡片\n\n"
        "本次抓取未成功。\n\n"
        f"原因: {error_text}\n\n"
    )


def _ensure_required_sections(markdown_text: str) -> str:
    text = markdown_text or ""
    existing_sections = {
        match.group(1).strip()
        for match in re.finditer(r"^#\s+(.+?)\s*$", text, flags=re.M)
    }
    missing_sections = [section for section in REQUIRED_SECTIONS if section not in existing_sections]
    if not missing_sections:
        return text

    suffix = "".join(_placeholder_section(section) for section in missing_sections)
    if text and not text.endswith("\n"):
        text += "\n"
    return text + suffix


def _append_stage_error_sections(markdown_text: str, stage_errors: dict) -> str:
    text = markdown_text or ""
    existing_sections = {
        match.group(1).strip()
        for match in re.finditer(r"^#\s+(.+?)\s*$", text, flags=re.M)
    }
    extra_sections = []
    for stage_name, section_name in STAGE_SECTION_MAP.items():
        error_text = (stage_errors.get(stage_name) or "").strip()
        if error_text and section_name not in existing_sections:
            extra_sections.append(_error_placeholder_section(section_name, error_text))
            existing_sections.add(section_name)
    if not extra_sections:
        return text
    if text and not text.endswith("\n"):
        text += "\n"
    return text + "".join(extra_sections)


def _run_stage(stage_name: str, func, *args, **kwargs):
    try:
        func(*args, **kwargs)
        return None
    except Exception as exc:
        message = _format_error_message(exc)
        print(f"{stage_name} 失败: {message}")
        return message


def _format_error_message(exc: Exception) -> str:
    message = getattr(exc, "msg", "") or str(exc) or exc.__class__.__name__
    message = message.split("Stacktrace:", 1)[0].strip()
    message = re.sub(r"\s+\(Session info:.*", "", message).strip()
    return message or exc.__class__.__name__


def _fallback_markdown(stage_errors: dict) -> str:
    details = []
    for stage_name, error_text in stage_errors.items():
        if error_text:
            details.append(f"- {stage_name}: {error_text}")
    detail_block = "\n".join(details) if details else "- 无详细错误信息"
    return (
        "# 万有预报\n\n"
        "## 本期说明\n\n"
        "本次运行已完成富文本导出流程，但公开网站抓取未取得可用内容。"
        "请检查网络连通性、校园站点可访问性或登录态后重试。\n\n"
        "抓取阶段记录：\n\n"
        f"{detail_block}\n\n"
        "# 教务通知\n\n## 占位卡片\n\n等待下次抓取结果。\n\n"
        "# 图书馆信息\n\n## 占位卡片\n\n等待下次抓取结果。\n\n"
        "# 学生会信息\n\n## 占位卡片\n\n等待下次抓取结果。\n\n"
        "# 青年科协信息\n\n## 占位卡片\n\n等待下次抓取结果。\n\n"
        "# 学生社团信息\n\n## 占位卡片\n\n等待下次抓取结果。\n\n"
        "# 家园网信息\n\n## 占位卡片\n\n等待下次抓取结果。\n\n"
        "# 新清华学堂\n\n## 占位卡片\n\n等待下次抓取结果。\n\n"
        "# 物理系学术报告\n\n## 占位卡片\n\n等待下次抓取结果。\n\n"
        "# 学生公益信息\n\n## 占位卡片\n\n等待下次抓取结果。\n\n"
        "# 其他公众号信息\n\n## 占位卡片\n\n等待下次抓取结果。\n"
    )


def convert_markdown_to_docx(markdown_path: str, docx_path: str, base_images_dir: str):
    import pypandoc

    pypandoc.convert_file(
        markdown_path,
        to="docx",
        outputfile=docx_path,
        extra_args=[
            "--from",
            "markdown+raw_html",
            config.PANDOC_RESOURCE_PATH_TEMPLATE.format(images_dir=base_images_dir),
            "--reference-doc",
            "template.docx",
        ],
    )


def run_pipeline(
    *,
    username: str = "",
    password: str = "",
    info_username: str = "",
    info_password: str = "",
    myhome_username: str = "",
    myhome_password: str = "",
    public_only: bool = False,
    include_wechat: bool = True,
    synthesize: bool = True,
    export_docx: bool = True,
    export_html: bool = True,
    export_agent_payload: bool = True,
    ranked_raw: bool = False,
    ranked_raw_skip_clean: bool = False,
    todo_richtext: bool = False,
    run_dir: str = "",
):
    previous_raw_collection_mode = getattr(config, "RAW_COLLECTION_MODE", False)
    previous_raw_skip_llm_clean = getattr(config, "RAW_SKIP_LLM_CLEAN", False)
    if ranked_raw_skip_clean:
        ranked_raw = True
    if ranked_raw:
        config.RAW_COLLECTION_MODE = True
        config.RAW_SKIP_LLM_CLEAN = bool(ranked_raw_skip_clean)
        synthesize = False
        export_docx = False
        export_html = False
        export_agent_payload = False

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    run_dir = run_dir or os.path.join(config.OUTPUT_DIR, timestamp)
    os.makedirs(run_dir, exist_ok=True)
    configure_filter_debug(os.path.join(run_dir, "debug"), reset=True)

    raw_markdown_path = os.path.join(run_dir, f"{config.OUTPUT_NAME_PREFIX}_{timestamp}_raw.md")
    final_markdown_path = os.path.join(run_dir, f"{config.OUTPUT_NAME_PREFIX}_{timestamp}.md")
    docx_path = os.path.join(run_dir, f"{config.OUTPUT_NAME_PREFIX}_{timestamp}.docx")
    html_path = os.path.join(run_dir, f"{config.OUTPUT_NAME_PREFIX}_{timestamp}.html")
    agent_payload_path = os.path.join(run_dir, f"{config.OUTPUT_NAME_PREFIX}_{timestamp}_agent.json")
    ranked_raw_path = os.path.join(run_dir, f"{config.OUTPUT_NAME_PREFIX}_{timestamp}_ranked_raw.md")
    todo_selected_raw_path = os.path.join(run_dir, f"{config.OUTPUT_NAME_PREFIX}_{timestamp}_todo_selected_raw.md")
    if ranked_raw_skip_clean:
        ranked_raw_path = os.path.join(run_dir, f"{config.OUTPUT_NAME_PREFIX}_{timestamp}_ranked_raw_no_clean.md")
    filename_jpg = f"_{config.OUTPUT_NAME_PREFIX}_{timestamp}"
    base_images_dir = os.path.join(run_dir, config.IMAGES_DIR_PREFIX)

    collect_full_content = ranked_raw or todo_richtext

    if config.LLM_LOG_PATH:
        config.LLM_LOG_PATH = os.path.join(run_dir, "llm_decisions.jsonl")

    credentials = {
        "info": {
            "username": info_username or username,
            "password": info_password or password,
        },
        "myhome": {
            "username": myhome_username or username,
            "password": myhome_password or password,
        },
    }

    if not public_only and (
        not credentials["info"]["username"]
        or not credentials["info"]["password"]
        or not credentials["myhome"]["username"]
        or not credentials["myhome"]["password"]
    ):
        prompted = prompt_credentials()
        for site_name in ("info", "myhome"):
            credentials[site_name]["username"] = credentials[site_name]["username"] or prompted[site_name]["username"]
            credentials[site_name]["password"] = credentials[site_name]["password"] or prompted[site_name]["password"]

    stage_errors = {}

    with open(raw_markdown_path, "w", encoding="utf-8") as doc:
        if not public_only:
            debug_dir = os.path.join(run_dir, "debug")
            auth_username = credentials["info"]["username"] or credentials["myhome"]["username"]
            auth_password = credentials["info"]["password"] or credentials["myhome"]["password"]
            if (
                credentials["info"]["username"]
                and credentials["myhome"]["username"]
                and credentials["info"]["username"] != credentials["myhome"]["username"]
            ) or (
                credentials["info"]["password"]
                and credentials["myhome"]["password"]
                and credentials["info"]["password"] != credentials["myhome"]["password"]
            ):
                print("检测到教务和家园网凭据不同；当前已改为共享统一认证，会优先使用教务凭据。")

            shared_browser = None
            auth_error = None
            try:
                shared_browser = authenticate_shared_browser(
                    auth_username,
                    auth_password,
                    debug_dir,
                    config.URL_INFO,
                    stage_label="统一认证",
                )
            except Exception as exc:
                auth_error = _format_error_message(exc)

            if shared_browser is None:
                stage_errors["crawl_info"] = auth_error or "统一认证失败"
                stage_errors["crawl_myhome"] = auth_error or "统一认证失败"
            else:
                try:
                    stage_errors["crawl_info"] = _run_stage(
                        "crawl_info",
                        crawl_info,
                        doc,
                        base_images_dir,
                        browser=shared_browser,
                    )
                    stage_errors["crawl_myhome"] = _run_stage(
                        "crawl_myhome",
                        crawl_myhome,
                        doc,
                        base_images_dir,
                        browser=shared_browser,
                    )
                finally:
                    try:
                        shared_browser.quit()
                    except Exception:
                        pass
        stage_errors["crawl_lib"] = _run_stage("crawl_lib", crawl_lib, doc, base_images_dir)
        stage_errors["crawl_hall"] = _run_stage("crawl_hall", crawl_hall, doc, filename_jpg, base_images_dir)
        stage_errors["crawl_physics"] = _run_stage("crawl_physics", crawl_physics, doc, base_images_dir)

        if include_wechat:
            recent_days = getattr(config, "WECHAT_MAIN_RECENT_DAYS", 7)
            try:
                items = collect_wechat_items(days_limit=recent_days)
                if items:
                    write_sectioned_md_stream(
                        items,
                        doc,
                        include_content=collect_full_content,
                    )
            except Exception as exc:
                print(f"公众号抓取失败: {_format_error_message(exc)}")

    with open(raw_markdown_path, "r", encoding="utf-8") as f:
        raw_markdown = f.read()
    if not raw_markdown.strip() and not ranked_raw:
        raw_markdown = _fallback_markdown(stage_errors)
    if not ranked_raw:
        raw_markdown = _append_stage_error_sections(raw_markdown, stage_errors)
        raw_markdown = _ensure_required_sections(raw_markdown)
    with open(raw_markdown_path, "w", encoding="utf-8") as f:
        f.write(raw_markdown)

    if ranked_raw:
        final_markdown = build_ranked_raw_markdown(
            raw_markdown,
            current_markdown_path=raw_markdown_path,
            clean_with_llm=False,
        )
        final_markdown_path = ranked_raw_path
    elif todo_richtext:
        print("正在生成 ranked raw，为最终富文本挑选各版块高分信息...")
        ranked_markdown = build_ranked_raw_markdown(
            raw_markdown,
            current_markdown_path=raw_markdown_path,
            clean_with_llm=False,
        )
        with open(ranked_raw_path, "w", encoding="utf-8") as f:
            f.write(ranked_markdown)

        print("正在按 README TODO 标准选取各版块 3-5 条核心信息...")
        selected_raw_markdown = build_selected_raw_markdown_from_ranked(ranked_markdown)
        with open(todo_selected_raw_path, "w", encoding="utf-8") as f:
            f.write(selected_raw_markdown)

        print("正在将入选条目合成为最终富文本万有预报...")
        if synthesize:
            selected_raw_markdown = clean_markdown_document_with_llm(
                selected_raw_markdown,
                source_prefix="最终富文本清洗",
            )
            final_markdown = build_augmented_markdown(
                selected_raw_markdown,
                current_markdown_path=todo_selected_raw_path,
            )
        else:
            final_markdown = selected_raw_markdown
        final_markdown = decorate_markdown_with_theme(final_markdown, final_markdown_path)
    else:
        if synthesize:
            cleaned_raw_markdown = clean_markdown_document_with_llm(raw_markdown, source_prefix="最终富文本清洗")
            final_markdown = build_augmented_markdown(cleaned_raw_markdown, current_markdown_path=raw_markdown_path)
        else:
            final_markdown = raw_markdown
        final_markdown = decorate_markdown_with_theme(final_markdown, final_markdown_path)
    with open(final_markdown_path, "w", encoding="utf-8") as f:
        f.write(final_markdown)

    if export_docx and getattr(config, "OUTPUT_DOCX_ENABLED", True):
        try:
            convert_markdown_to_docx(final_markdown_path, docx_path, base_images_dir)
        except Exception as exc:
            print(f"DOCX 导出失败: {exc}")
            docx_path = ""
    else:
        docx_path = ""

    if export_html and getattr(config, "OUTPUT_H5_ENABLED", True):
        export_h5(final_markdown_path, html_path, title=getattr(config, "H5_TITLE", "万有预报"))
    else:
        html_path = ""

    if export_agent_payload and getattr(config, "OUTPUT_AGENT_PAYLOAD_ENABLED", True):
        export_browser_agent_payload(final_markdown_path, agent_payload_path, html_path=html_path)
    else:
        agent_payload_path = ""

    filter_summary_path = finalize_filter_debug()

    outputs = [f"Markdown: {final_markdown_path}"]
    if todo_richtext:
        outputs.append(f"Ranked raw: {ranked_raw_path}")
        outputs.append(f"Selected raw: {todo_selected_raw_path}")
    if docx_path:
        outputs.append(f"DOCX: {docx_path}")
    if html_path:
        outputs.append(f"H5: {html_path}")
    if agent_payload_path:
        outputs.append(f"Agent payload: {agent_payload_path}")
    if filter_summary_path:
        outputs.append(f"Filter debug: {filter_summary_path}")
    print(" | ".join(outputs))
    config.RAW_COLLECTION_MODE = previous_raw_collection_mode
    config.RAW_SKIP_LLM_CLEAN = previous_raw_skip_llm_clean

    return {
        "run_dir": run_dir,
        "raw_markdown_path": raw_markdown_path,
        "final_markdown_path": final_markdown_path,
        "docx_path": docx_path,
        "html_path": html_path,
        "agent_payload_path": agent_payload_path,
        "filter_debug_path": os.path.join(run_dir, "debug", "filter_decisions.jsonl"),
        "filter_summary_path": filter_summary_path,
        "ranked_raw_path": ranked_raw_path if (ranked_raw or todo_richtext) else "",
        "ranked_raw_skip_clean": ranked_raw_skip_clean,
        "todo_selected_raw_path": todo_selected_raw_path if todo_richtext else "",
    }


def main():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    run_pipeline()


if __name__ == "__main__":
    main()
