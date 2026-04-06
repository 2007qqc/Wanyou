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


def main():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    run_dir = os.path.join(config.OUTPUT_DIR, timestamp)
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

    username, password = prompt_credentials()

    with open(raw_markdown_path, "w", encoding="utf-8") as doc:
        crawl_info(doc, base_images_dir, username, password)
        crawl_myhome(doc, base_images_dir, username, password)
        crawl_lib(doc, base_images_dir)
        crawl_hall(doc, filename_jpg, base_images_dir)
        crawl_physics(doc, base_images_dir)
        try:
            recent_days = getattr(config, "WECHAT_MAIN_RECENT_DAYS", 7)
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

    final_markdown = build_augmented_markdown(raw_markdown)
    with open(final_markdown_path, "w", encoding="utf-8") as f:
        f.write(final_markdown)

    if getattr(config, "OUTPUT_DOCX_ENABLED", True):
        convert_markdown_to_docx(final_markdown_path, docx_path, base_images_dir)

    if getattr(config, "OUTPUT_H5_ENABLED", True):
        export_h5(final_markdown_path, html_path, title=getattr(config, "H5_TITLE", "万有预报"))

    if getattr(config, "OUTPUT_AGENT_PAYLOAD_ENABLED", True):
        export_browser_agent_payload(final_markdown_path, agent_payload_path, html_path=html_path)

    print(f"Markdown 已保存至: {final_markdown_path}")
    if getattr(config, "OUTPUT_DOCX_ENABLED", True):
        print(f"DOCX 已保存至: {docx_path}")
    if getattr(config, "OUTPUT_H5_ENABLED", True):
        print(f"H5 已保存至: {html_path}")
    if getattr(config, "OUTPUT_AGENT_PAYLOAD_ENABLED", True):
        print(f"Agent payload 已保存至: {agent_payload_path}")


if __name__ == "__main__":
    main()
