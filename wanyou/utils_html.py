import html as html_lib
import os
import re
from urllib.parse import urljoin, urlparse

import html2text
import config
from wanyou.utils_llm import chat_complete


BLOCK_TAGS = ("p", "div", "section", "article", "li", "ul", "ol", "table", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "br")


def normalize_resource_urls(html_text, base_url):
    parsed = urlparse(base_url)
    base_origin = f"{parsed.scheme}://{parsed.netloc}"

    def repl(match):
        src = match.group(1).strip()
        if src.startswith("http://localhost") or src.startswith("https://localhost"):
            src = base_origin + src.replace("http://localhost", "").replace("https://localhost", "")
        elif src.startswith("//"):
            scheme = base_origin.split(":")[0]
            src = f"{scheme}:{src}"
        elif not src.startswith("http"):
            src = urljoin(base_url, src)
        return f'src="{src}"'

    return re.sub(r'src="([^"]+)"', repl, html_text)



def download_images_and_rewrite(html_text, base_url, session, images_dir, image_counter, image_prefix, referer):
    def repl(match):
        src = match.group(1).strip()
        if not src:
            return match.group(0)
        absolute_url = src
        if src.startswith("http://localhost") or src.startswith("https://localhost"):
            parsed = urlparse(base_url)
            base_origin = f"{parsed.scheme}://{parsed.netloc}"
            absolute_url = base_origin + src.replace("http://localhost", "").replace("https://localhost", "")
        elif src.startswith("//"):
            scheme = urlparse(base_url).scheme or "https"
            absolute_url = f"{scheme}:{src}"
        elif not src.startswith("http"):
            absolute_url = urljoin(base_url, src)

        try:
            headers = {"Referer": referer, "User-Agent": config.USER_AGENT, "Accept": "image/*,*/*;q=0.8"}
            resp = session.get(absolute_url, headers=headers, stream=True, timeout=15)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            ext = ".jpg"
            if "png" in content_type:
                ext = ".png"
            elif "gif" in content_type:
                ext = ".gif"
            elif "webp" in content_type:
                ext = ".webp"
            elif "jpeg" in content_type:
                ext = ".jpg"
            else:
                path_ext = os.path.splitext(urlparse(absolute_url).path)[1]
                if path_ext:
                    ext = path_ext

            os.makedirs(images_dir, exist_ok=True)
            image_counter[0] += 1
            filename = f"{image_prefix}_{image_counter[0]:04d}{ext}"
            local_path = os.path.join(images_dir, filename)
            with open(local_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return f'src="{local_path}"'
        except Exception:
            return match.group(0)

    return re.sub(r'src="([^"]+)"', repl, html_text)



def normalize_table_html(table_html):
    lines = [line.lstrip() for line in table_html.splitlines()]
    normalized = "\n".join(lines).strip()
    return normalized



def strip_html_tags(text):
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text



def table_html_to_markdown(table_html):
    rows = re.findall(r"<tr[\s\S]*?</tr>", table_html, flags=re.I)
    if not rows:
        return table_html
    table = []
    for row in rows:
        cells = re.findall(r"<t[hd][\s\S]*?</t[hd]>", row, flags=re.I)
        if not cells:
            continue
        table.append([strip_html_tags(c) for c in cells])
    if not table:
        return table_html
    max_cols = max(len(r) for r in table)
    for r in table:
        while len(r) < max_cols:
            r.append("")
    header = [c.replace("|", "\\|") for c in table[0]]
    sep = ["---" for _ in range(max_cols)]
    body = [[c.replace("|", "\\|") for c in row] for row in table[1:]]
    lines = []
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(sep) + " |")
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)



def extract_tables(html_text):
    tables = []

    def repl(match):
        normalized = normalize_table_html(match.group(0))
        tables.append(table_html_to_markdown(normalized))
        return f"[[TABLE_{len(tables)}]]"

    stripped = re.sub(r"<table[\s\S]*?</table>", repl, html_text, flags=re.I)
    return stripped, tables



def restore_tables(text, tables):
    for i, table_html in enumerate(tables, start=1):
        token = f"[[TABLE_{i}]]"
        text = text.replace(token, f"\n\n{table_html}\n\n")
    return text



def html_to_markdown(container, base_url, session, images_dir, image_counter, image_prefix, referer):
    container_html = container.get_attribute("outerHTML")
    container_html = normalize_resource_urls(container_html, base_url)
    if getattr(config, "RAW_COLLECTION_MODE", False):
        container_html = re.sub(r"<img\b[^>]*>", "", container_html, flags=re.I)
    else:
        container_html = download_images_and_rewrite(
            container_html, base_url, session, images_dir, image_counter, image_prefix, referer
        )

    handler = html2text.HTML2Text()
    handler.ignore_images = bool(getattr(config, "RAW_COLLECTION_MODE", False))
    handler.body_width = 0
    handler.single_line_break = True
    handler.bypass_tables = True
    html_without_tables, tables = extract_tables(container_html)
    text = handler.handle(html_without_tables)
    text = restore_tables(text, tables)
    text = re.sub("\n", "\n\n", text)
    return text



def _strip_residual_markup(text):
    cleaned = (text or "").replace("\ufeff", "")
    cleaned = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", cleaned)
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"(?i)</?(?:" + "|".join(BLOCK_TAGS) + r")[^>]*>", "\n", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html_lib.unescape(cleaned)
    cleaned = cleaned.replace("&nbsp;", " ")
    cleaned = re.sub(r"!\[([^\]]*)\]\(([^)]*)\)", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\(([^)]*)\)", r"\1", cleaned)
    cleaned = re.sub(r"`{1,3}([^`]+)`{1,3}", r"\1", cleaned)
    cleaned = re.sub(r"(?m)^\s{0,3}>\s?", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*[-*_]{3,}\s*$", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*#{1,6}\s*([^#\n]+?)\s*$", r"### \1", cleaned)
    cleaned = re.sub(r"(?<!\*)\*\*([^*\n]+)\*\*(?!\*)", r"\1", cleaned)
    cleaned = re.sub(r"(?<!_)__([^_\n]+)__(?!_)", r"\1", cleaned)
    cleaned = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", cleaned)
    cleaned = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", cleaned)
    cleaned = re.sub(r"\\([*_#`>\-])", r"\1", cleaned)
    cleaned = re.sub(r"\n[ \t]+", "\n", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()



def _rule_clean_markdown(text):
    cleaned = _strip_residual_markup(text)
    cleaned = re.sub(r"(?m)^[ \t]*\*{3,}[ \t]*$", "", cleaned)
    cleaned = re.sub(r"\*{4,}", "", cleaned)
    cleaned = re.sub(r"\n(?:[ \t]*\n)+", "\n\n", cleaned)
    return cleaned.strip()


def _clean_quality_score(text):
    candidate = (text or "").strip()
    chinese = len(re.findall(r"[\u4e00-\u9fff]", candidate))
    english_noise = len(re.findall(r"Source:|Markdown:|Content:|Status:|Unknown", candidate, flags=re.I))
    html_noise = len(re.findall(r"<[a-zA-Z/][^>]*>", candidate))
    return chinese * 3 + len(candidate) - english_noise * 20 - html_noise * 10



def _normalize_body_headings(text, title=""):
    lines = (text or "").splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)

    if lines:
        first_line = lines[0].strip()
        first_heading = re.sub(r"^#+\s*", "", first_line).strip()
        if first_line.startswith("#") and title and first_heading == title.strip():
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)

    normalized = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            heading_text = re.sub(r"^#+\s*", "", stripped).strip()
            if heading_text:
                normalized.append(f"### {heading_text}")
                continue
        normalized.append(line)
    return "\n".join(normalized).strip()



def clean_crawled_markdown(text, source="", *, use_llm=False):
    cleaned = _rule_clean_markdown(text)
    if not cleaned:
        return ""
    if not use_llm or getattr(config, "RAW_SKIP_LLM_CLEAN", False):
        return cleaned

    prompt = (
        "Clean the Markdown formatting without changing facts.\n"
        "Remove residual HTML tags, broken Markdown markers, stray emphasis, repeated blank lines, and raw markup noise.\n"
        "Keep headings, lists, dates, names, links, and paragraph order.\n"
        "Return Markdown only."
    )
    user_prompt = f"Source: {source or 'crawler'}\n\nMarkdown:\n{cleaned[:3000]}"
    result = chat_complete(
        prompt,
        user_prompt,
        max_tokens=500,
        temperature=0,
        task_label=f"正在清洗正文格式：{(source or '正文')[:24]}",
    )
    if result:
        candidate = _rule_clean_markdown(result)
        if _clean_quality_score(candidate) >= _clean_quality_score(cleaned):
            cleaned = candidate
    return cleaned


def clean_markdown_document_with_llm(markdown_text, source_prefix="final"):
    sections = []
    current_section = None
    current_item = None

    def finish_item():
        nonlocal current_item
        if current_item is not None and current_section is not None:
            current_section["items"].append(current_item)
            current_item = None

    for raw_line in (markdown_text or "").splitlines():
        line = raw_line.rstrip()
        if line.startswith("# "):
            finish_item()
            if current_section is not None:
                sections.append(current_section)
            current_section = {"title": line[2:].strip(), "items": []}
            continue
        if line.startswith("## "):
            if current_section is None:
                current_section = {"title": "未分类", "items": []}
            finish_item()
            current_item = {"title": line[3:].strip(), "body_lines": []}
            continue
        if current_item is not None:
            current_item["body_lines"].append(raw_line)

    finish_item()
    if current_section is not None:
        sections.append(current_section)

    rendered_sections = []
    for section in sections:
        parts = [f"# {section['title']}", ""]
        for item in section["items"]:
            title = item["title"]
            body = "\n".join(item.get("body_lines", [])).strip()
            if not body:
                continue
            cleaned = clean_crawled_markdown(
                body,
                source=f"{source_prefix}:{title}",
                use_llm=True,
            )
            cleaned = _normalize_body_headings(cleaned, title=title)
            cleaned = _rule_clean_markdown(cleaned)
            parts.append(f"## {title}")
            parts.append("")
            parts.append(cleaned)
            parts.append("")
        rendered_sections.append("\n".join(parts).rstrip())
    return "\n\n".join(section for section in rendered_sections if section).strip() + "\n"



def save_content(titles, full_texts, doc):
    for title, full_text in zip(titles, full_texts):
        cleaned_text = clean_crawled_markdown(full_text, source=title) or _rule_clean_markdown(full_text)
        cleaned_text = _normalize_body_headings(cleaned_text, title=title)
        cleaned_text = _rule_clean_markdown(cleaned_text)
        doc.write(f"## {title}\n\n")
        doc.write(cleaned_text.rstrip())
        doc.write("\n\n")
