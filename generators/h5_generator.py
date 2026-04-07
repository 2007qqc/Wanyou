import html
import os
import re
from typing import List

import config


def _score_text(text: str) -> tuple[int, int]:
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    latin1_noise = sum(1 for ch in text if "\u00c0" <= ch <= "\u00ff")
    return cjk, -latin1_noise


def _maybe_fix_mojibake(text: str) -> str:
    cleaned = text.replace("\ufeff", "").strip()
    try:
        repaired = cleaned.encode("latin1").decode("utf-8")
    except Exception:
        return cleaned
    if _score_text(repaired) > _score_text(cleaned):
        return repaired
    return cleaned


def _should_skip_line(text: str) -> bool:
    stripped = text.strip()
    cjk, latin1_penalty = _score_text(stripped)
    latin1_noise = -latin1_penalty
    if not stripped or stripped == "\ufeff":
        return True
    if stripped.startswith("[English]("):
        return True
    if stripped.startswith("[![]("):
        return True
    if stripped.startswith("* [") and "](" in stripped:
        return True
    if " > " in stripped and "](" in stripped:
        return True
    if latin1_noise >= 4 and cjk <= latin1_noise:
        return True
    return False


def _resolve_image_src(src: str, markdown_path: str, output_path: str) -> str:
    cleaned = src.strip().strip("<>").strip('"').strip("'")
    if not cleaned:
        return cleaned
    if re.match(r"^(https?:)?//", cleaned):
        return cleaned

    normalized = cleaned.replace("\\", os.sep).replace("/", os.sep)
    candidates = []

    if os.path.isabs(normalized):
        candidates.append(normalized)
    else:
        candidates.append(os.path.normpath(os.path.join(os.getcwd(), normalized)))
        candidates.append(os.path.normpath(os.path.join(os.path.dirname(markdown_path), normalized)))

    resolved = next((path for path in candidates if os.path.exists(path)), candidates[0])
    relative = os.path.relpath(resolved, start=os.path.dirname(output_path))
    return relative.replace("\\", "/")


def markdown_to_h5_html(markdown_text: str, markdown_path: str, output_path: str, title: str = "") -> str:
    page_title = title or getattr(config, "H5_TITLE", "万有预报")
    blocks: List[str] = []
    article_open = False
    section_open = False

    for line in markdown_text.splitlines():
        stripped = _maybe_fix_mojibake(line)
        if not stripped:
            continue
        if _should_skip_line(stripped):
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
            src = html.escape(_resolve_image_src(image_match.group(1), markdown_path, output_path))
            blocks.append(f"<figure class='figure'><img src='{src}' alt='推送配图' loading='lazy' /></figure>")
            continue

        if stripped.startswith("链接: "):
            url = html.escape(stripped[4:].strip())
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

    html_text = markdown_to_h5_html(markdown_text, markdown_path=markdown_path, output_path=output_path, title=title)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_text)
    return output_path
