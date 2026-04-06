import html
import os
import re
from typing import List

import config


def markdown_to_h5_html(markdown_text: str, title: str = "") -> str:
    page_title = title or getattr(config, "H5_TITLE", "万有预报")
    blocks: List[str] = []
    article_open = False
    section_open = False

    for line in markdown_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("# "):
            if article_open:
                blocks.append("</article>")
                article_open = False
            if section_open:
                blocks.append("</section>")
            blocks.append(f"<section class='section'><h2>{html.escape(stripped[2:].strip())}</h2>")
            section_open = True
            continue

        if stripped.startswith("## "):
            if article_open:
                blocks.append("</article>")
            blocks.append(f"<article class='card'><h3>{html.escape(stripped[3:].strip())}</h3>")
            article_open = True
            continue

        image_match = re.match(r"!\[[^\]]*\]\(([^)]+)\)", stripped)
        if image_match:
            src = html.escape(image_match.group(1).strip())
            blocks.append("<figure class='figure'>" f"<img src='{src}' alt='推送配图' loading='lazy' />" "</figure>")
            continue

        if stripped.startswith("链接: "):
            url = html.escape(stripped[3:].strip())
            blocks.append(f"<p><a href='{url}'>{url}</a></p>")
            continue

        if re.match(r"^https?://", stripped):
            url = html.escape(stripped)
            blocks.append(f"<p><a href='{url}'>{url}</a></p>")
            continue

        blocks.append(f"<p>{html.escape(stripped)}</p>")

    if article_open:
        blocks.append("</article>")
    if section_open:
        blocks.append("</section>")

    body_html = "\n".join(blocks)

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(page_title)}</title>
  <style>
    :root {{
      --bg: linear-gradient(180deg, #f7f1e3 0%, #fefcf7 100%);
      --paper: rgba(255, 252, 245, 0.95);
      --ink: #1c2a39;
      --muted: #6d7a88;
      --accent: #1d6f5f;
      --border: rgba(29, 111, 95, 0.16);
      --shadow: 0 18px 50px rgba(28, 42, 57, 0.10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Noto Serif SC", "Source Han Serif SC", serif;
      background: var(--bg);
      color: var(--ink);
    }}
    .page {{
      max-width: 760px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }}
    .hero {{
      padding: 28px 22px;
      border-radius: 24px;
      background:
        radial-gradient(circle at top right, rgba(29,111,95,0.16), transparent 34%),
        linear-gradient(135deg, rgba(255,255,255,0.96), rgba(252,248,240,0.92));
      box-shadow: var(--shadow);
      margin-bottom: 20px;
    }}
    .hero h1 {{ margin: 0 0 8px; font-size: 34px; line-height: 1.1; }}
    .hero p {{ margin: 0; color: var(--muted); font-size: 15px; }}
    .section {{ margin-top: 26px; }}
    .section h2 {{ margin: 0 0 12px; font-size: 24px; }}
    .card {{
      background: var(--paper);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 18px 16px;
      margin: 0 0 14px;
      box-shadow: var(--shadow);
    }}
    .card h3 {{ margin: 0 0 10px; font-size: 20px; }}
    p {{ margin: 10px 0; line-height: 1.8; word-break: break-word; }}
    a {{ color: var(--accent); }}
    .figure {{ margin: 14px 0; }}
    .figure img {{
      display: block;
      width: 100%;
      border-radius: 16px;
      border: 1px solid var(--border);
    }}
    @media (max-width: 640px) {{
      .hero h1 {{ font-size: 28px; }}
      .section h2 {{ font-size: 22px; }}
      .card h3 {{ font-size: 18px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="hero">
      <h1>{html.escape(page_title)}</h1>
      <p>从校园抓取到推送制作，一次生成可用于 H5 与秀米整理的内容底稿。</p>
    </header>
    {body_html}
  </main>
</body>
</html>
'''


def export_h5(markdown_path: str, output_path: str, title: str = "") -> str:
    with open(markdown_path, "r", encoding="utf-8") as f:
        markdown_text = f.read()

    html_text = markdown_to_h5_html(markdown_text, title=title)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_text)
    return output_path