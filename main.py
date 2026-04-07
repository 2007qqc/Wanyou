import datetime
import os

import pypandoc

import config
from generators.browser_agent import export_browser_agent_payload
from generators.h5_generator import export_h5
from wanyou.crawlers_hall import crawl_hall
from wanyou.crawlers_info import crawl_info
from wanyou.crawlers_lib import crawl_lib
from wanyou.crawlers_myhome import crawl_myhome
from wanyou.crawlers_physics import crawl_physics
from wanyou.synthesizer import build_augmented_markdown
from wanyou.utils_auth import prompt_credentials
from wanyou.wechat_pipeline import collect_wechat_items, write_md_stream


def _run_stage(stage_name: str, func, *args):
    try:
        func(*args)
        print(f"{stage_name} 完成")
        return None
    except Exception as exc:
        print(f"{stage_name} 失败: {exc}")
        return str(exc)


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
        "# 学生社区\n\n## 占位卡片\n\n等待下次抓取结果。\n\n"
        "# 图书馆信息\n\n## 占位卡片\n\n等待下次抓取结果。\n\n"
        "# 新清华学堂\n\n## 占位卡片\n\n等待下次抓取结果。\n\n"
        "# 物理系学术报告\n\n## 占位卡片\n\n等待下次抓取结果。\n\n"
        "# 公众号信息\n\n## 占位卡片\n\n等待下次抓取结果。\n"
    )


def convert_markdown_to_docx(markdown_path: str, docx_path: str, base_images_dir: str):
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
    public_only: bool = False,
    include_wechat: bool = True,
    synthesize: bool = True,
    export_docx: bool = True,
    export_html: bool = True,
    export_agent_payload: bool = True,
    run_dir: str = "",
):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    run_dir = run_dir or os.path.join(config.OUTPUT_DIR, timestamp)
    os.makedirs(run_dir, exist_ok=True)

    raw_markdown_path = os.path.join(run_dir, f"{config.OUTPUT_NAME_PREFIX}_{timestamp}_raw.md")
    final_markdown_path = os.path.join(run_dir, f"{config.OUTPUT_NAME_PREFIX}_{timestamp}.md")
    docx_path = os.path.join(run_dir, f"{config.OUTPUT_NAME_PREFIX}_{timestamp}.docx")
    html_path = os.path.join(run_dir, f"{config.OUTPUT_NAME_PREFIX}_{timestamp}.html")
    agent_payload_path = os.path.join(run_dir, f"{config.OUTPUT_NAME_PREFIX}_{timestamp}_agent.json")
    filename_jpg = f"_{config.OUTPUT_NAME_PREFIX}_{timestamp}"
    base_images_dir = os.path.join(run_dir, config.IMAGES_DIR_PREFIX)

    if config.LLM_LOG_PATH:
        config.LLM_LOG_PATH = os.path.join(run_dir, "llm_decisions.jsonl")

    if not public_only and (not username or not password):
        username, password = prompt_credentials()

    stage_errors = {}

    with open(raw_markdown_path, "w", encoding="utf-8") as doc:
        if not public_only:
            stage_errors["crawl_info"] = _run_stage("crawl_info", crawl_info, doc, base_images_dir, username, password)
            stage_errors["crawl_myhome"] = _run_stage("crawl_myhome", crawl_myhome, doc, base_images_dir, username, password)
        stage_errors["crawl_lib"] = _run_stage("crawl_lib", crawl_lib, doc, base_images_dir)
        stage_errors["crawl_hall"] = _run_stage("crawl_hall", crawl_hall, doc, filename_jpg, base_images_dir)
        stage_errors["crawl_physics"] = _run_stage("crawl_physics", crawl_physics, doc, base_images_dir)

        if include_wechat:
            recent_days = getattr(config, "WECHAT_MAIN_RECENT_DAYS", 7)
            try:
                items = collect_wechat_items(days_limit=recent_days)
                if items:
                    write_md_stream(
                        items,
                        doc,
                        include_content=getattr(config, "WECHAT_FETCH_CONTENT", True),
                        header=f"# 公众号信息（最近 {recent_days} 天）",
                    )
            except Exception as exc:
                print(f"公众号抓取失败: {exc}")

    with open(raw_markdown_path, "r", encoding="utf-8") as f:
        raw_markdown = f.read()
    if not raw_markdown.strip():
        raw_markdown = _fallback_markdown(stage_errors)
        with open(raw_markdown_path, "w", encoding="utf-8") as f:
            f.write(raw_markdown)

    final_markdown = build_augmented_markdown(raw_markdown) if synthesize else raw_markdown
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

    print(f"Markdown 已保存至: {final_markdown_path}")
    if docx_path:
        print(f"DOCX 已保存至: {docx_path}")
    if html_path:
        print(f"H5 已保存至: {html_path}")
    if agent_payload_path:
        print(f"Agent payload 已保存至: {agent_payload_path}")

    return {
        "run_dir": run_dir,
        "raw_markdown_path": raw_markdown_path,
        "final_markdown_path": final_markdown_path,
        "docx_path": docx_path,
        "html_path": html_path,
        "agent_payload_path": agent_payload_path,
    }


def main():
    run_pipeline()


if __name__ == "__main__":
    main()
