import html as html_lib
import os
import re
from urllib.parse import urljoin, urlparse

import html2text
import config


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
    header = table[0]
    header = [c.replace("|", "\\|") for c in header]
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
    container_html = download_images_and_rewrite(
        container_html, base_url, session, images_dir, image_counter, image_prefix, referer
    )

    handler = html2text.HTML2Text()
    handler.body_width = 0
    handler.single_line_break = True
    handler.bypass_tables = True
    html_without_tables, tables = extract_tables(container_html)
    text = handler.handle(html_without_tables)
    text = restore_tables(text, tables)
    text = re.sub("\n", "\n\n", text)

    return text


def save_content(titles, full_texts, doc):
    for title, full_text in zip(titles, full_texts):
        doc.write(f"## {title}\n\n")
        doc.write(full_text.rstrip())
        doc.write("\n\n")
