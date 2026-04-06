import datetime
import os
import pypandoc

import config
from wanyou.crawlers_info import crawl_info
from wanyou.crawlers_myhome import crawl_myhome
from wanyou.crawlers_lib import crawl_lib
from wanyou.crawlers_hall import crawl_hall
from wanyou.wechat_pipeline import collect_wechat_items, write_md_stream
from wanyou.utils_auth import prompt_credentials


# 创建 md 文档

timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
run_dir = os.path.join(config.OUTPUT_DIR, timestamp)
os.makedirs(run_dir, exist_ok=True)

filenamemd = os.path.join(run_dir, f"{config.OUTPUT_NAME_PREFIX}_{timestamp}.md")
filenamedocx = os.path.join(run_dir, f"{config.OUTPUT_NAME_PREFIX}_{timestamp}.docx")
filename_jpg = f"_{config.OUTPUT_NAME_PREFIX}_{timestamp}"
base_images_dir = os.path.join(run_dir, config.IMAGES_DIR_PREFIX)

if config.LLM_LOG_PATH:
    config.LLM_LOG_PATH = os.path.join(run_dir, "llm_decisions.jsonl")

username, password = prompt_credentials()

with open(filenamemd, "w", encoding="utf-8") as doc:
    crawl_info(doc, base_images_dir, username, password)
    crawl_myhome(doc, base_images_dir, username, password)
    crawl_lib(doc, base_images_dir)
    crawl_hall(doc, filename_jpg, base_images_dir)
    try:
        recent_days = getattr(config, "WECHAT_MAIN_RECENT_DAYS", 7)
        items = collect_wechat_items(days_limit=recent_days)
        if items:
            write_md_stream(
                items,
                doc,
                include_content=getattr(config, "WECHAT_FETCH_CONTENT", True),
                header=f"# 公众号信息（最近{recent_days}天）",
            )
    except Exception as exc:
        print(f"公众号抓取失败：{exc}")

pypandoc.convert_file(
    filenamemd,
    to="docx",
    outputfile=filenamedocx,
    extra_args=[
        "--from",
        "markdown+raw_html",
        config.PANDOC_RESOURCE_PATH_TEMPLATE.format(images_dir=base_images_dir),
        "--reference-doc",
        "template.docx",
    ],
)
# 保存文件（按时间戳命名，避免重复）
print(f"文件已保存至：{filenamedocx}")
