"""Markdown 文档结构解析：`# 栏目` + `## 条目` 的极简解析器。

合成、raw 打分、公众号选稿补写和最终清洗都依赖同一套结构约定，抽到这里
避免各模块维护一份几乎相同的解析逻辑。
"""


def parse_markdown_document(markdown_text):
    sections = []
    current_section = None
    current_item = None

    for raw_line in (markdown_text or "").splitlines():
        line = raw_line.rstrip()
        if line.startswith("# "):
            if current_item and current_section is not None:
                current_section["items"].append(current_item)
                current_item = None
            if current_section is not None:
                sections.append(current_section)
            current_section = {"title": line[2:].strip(), "items": []}
            continue

        if line.startswith("## "):
            if current_section is None:
                current_section = {"title": "未分类", "items": []}
            if current_item is not None:
                current_section["items"].append(current_item)
            current_item = {"title": line[3:].strip(), "body_lines": []}
            continue

        if current_item is not None:
            current_item["body_lines"].append(raw_line)

    if current_item and current_section is not None:
        current_section["items"].append(current_item)
    if current_section is not None:
        sections.append(current_section)
    return sections
