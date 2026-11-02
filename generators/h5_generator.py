import html
import os
import re
import shutil
from typing import Dict, List, Tuple

import config
from generators.text_spans import highlight_time_spans
from wanyou.image_paths import clean_markdown_image_target, is_remote_or_data_image, resolve_existing_image_path
from wanyou.inline_images import embed_local_images


THEME_SOURCE_DIR = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "output",
        "万有预报 _ 2025-2026学年春季学期SRT学生报名即将截止_files",
    )
)
THEME_ASSET_SPECS = {
    "badge": ("0(1)", "badge.png"),
    "badge_mini": ("300", "badge-mini.png"),
}
THEME_DIR_NAME = "_theme"
THEME_BADGE_ALT = "物理系风格标识"
THEME_BADGE_MINI_ALT = "物理系风格标识-页尾"
HEADER_TITLE_LINE = "**万有预报**"
HEADER_SUBTITLE_LINE = "*清华大学物理系校园信息整理*"
FOOTER_LINE = "*万有预报，下期再见。*"
META_LABELS = {
    "日期",
    "时间",
    "地点",
    "票价",
    "发布日期",
    "报告时间",
    "报告地点",
    "报告人",
    "来源公众号",
    "作者",
    "链接",
    "摘要",
    "报告摘要",
}


def _score_text(text: str) -> tuple[int, int]:
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    latin1_noise = sum(1 for ch in text if "\u00c0" <= ch <= "\u00ff")
    return cjk, -latin1_noise



def _maybe_fix_mojibake(text: str) -> str:
    cleaned = (text or "").replace("\ufeff", "").strip()
    try:
        repaired = cleaned.encode("latin1").decode("utf-8")
    except Exception:
        return cleaned
    if _score_text(repaired) > _score_text(cleaned):
        return repaired
    return cleaned



def _safe_title(title: str) -> str:
    candidate = _maybe_fix_mojibake(title or getattr(config, "H5_TITLE", "万有预报"))
    if not candidate:
        return "万有预报"
    cjk, latin_penalty = _score_text(candidate)
    if cjk == 0 and -latin_penalty >= 3:
        return "万有预报"
    return candidate



def _theme_asset_output_dir(target_path: str) -> str:
    return os.path.join(os.path.dirname(target_path), THEME_DIR_NAME)



def ensure_theme_assets(target_path: str) -> Dict[str, str]:
    output_dir = _theme_asset_output_dir(target_path)
    os.makedirs(output_dir, exist_ok=True)
    copied = {}
    for name, (source_name, target_name) in THEME_ASSET_SPECS.items():
        source_path = os.path.join(THEME_SOURCE_DIR, source_name)
        if not os.path.exists(source_path):
            continue
        target_file = os.path.join(output_dir, target_name)
        if not os.path.exists(target_file):
            shutil.copyfile(source_path, target_file)
        copied[name] = target_file
    return copied



HIGHLIGHTS_TITLE_LINE = "# 本期要点速递"
HIGHLIGHTS_SECTION_TITLE = "本期要点速递"


def _fallback_highlights(text: str, limit: int = 5) -> List[str]:
    """从各条目的要点透视里拼「本期要点速递」（LLM 那条路返回空时用）。

    形如「无偿献血：11月7—8日8:00—14:00」：条目名 + 带日期的那一段。
    只取「要点透视」的第一个分句会得到「全校师生」这种没有信息量的碎片，
    所以这里在分句里挑**含日期**的那一句，并按日期从近到远排序。
    """

    import datetime as _dt

    from wanyou.date_ranges import parse_dates

    today = _dt.date.today()
    candidates: List[tuple] = []
    for section in re.split(r"^# ", text or "", flags=re.M)[1:]:
        for block in re.split(r"^## ", section, flags=re.M)[1:]:
            lines = block.split("\n")
            item_title = lines[0].strip()
            lede_match = re.search(r"要点透视[：:](.+)", block)
            if not item_title or not lede_match:
                continue
            short_title = item_title if len(item_title) <= 16 else item_title[:15].rstrip() + "…"
            lede = lede_match.group(1).strip()
            fragments = [frag.strip() for frag in re.split(r"[。；;]", lede) if frag.strip()]
            if not fragments:
                continue
            dates = sorted(d for d in parse_dates(lede, reference=today) if d >= today)
            if dates:
                fragment = next(
                    (frag for frag in fragments if parse_dates(frag, reference=today)),
                    fragments[0],
                )
                line = f"{short_title}：{fragment}"
                rank = (0, dates[0].toordinal())
            else:
                line = f"{short_title}：{fragments[0]}"
                rank = (1, 0)
            if len(line) > 46:
                line = line[:45] + "…"
            candidates.append((rank, line))

    candidates.sort(key=lambda pair: pair[0])
    picks: List[str] = []
    for _, line in candidates:
        if line not in picks:
            picks.append(line)
        if len(picks) >= limit:
            break
    return picks


_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-•·*]|\d{1,2}\s*[.、)])\s*")


def _strip_bullet_marker(line: str) -> str:
    """去掉行首的 "-"、序号，但绝不能碰「10月31日」里的数字。"""
    return _BULLET_PREFIX_RE.sub("", line).strip()


def _build_highlights(text: str, limit: int = 5) -> List[str]:
    """给「本期要点速递」写 5 条，只要当期最该先知道的事。"""
    ledes = re.findall(r"要点透视[：:](.+)", text or "")
    if not ledes:
        return []
    if getattr(config, "LLM_ENABLED", False):
        try:
            from wanyou.utils_llm import chat_complete

            result = chat_complete(
                "你在为清华大学物理系《万有预报》写开头的「本期要点速递」。\n"
                f"从下面这些要点里挑 {limit} 条最该先知道的（临近截止、时间临近、影响面大的优先），\n"
                "每条不超过 38 字，写成一句话，保留日期，不要编号、不要句号，按重要性排序。\n"
                "只输出若干行，每行一条。",
                "\n".join(ledes)[:4000],
                temperature=0,
                task_label="正在写本期要点速递",
            )
        except Exception:
            result = ""
        bullets = [_strip_bullet_marker(line) for line in (result or "").splitlines() if line.strip()]
        bullets = [b for b in bullets if 6 <= len(b) <= 60][:limit]
        if bullets:
            return bullets
    return _fallback_highlights(text, limit)


def _strip_previous_theme_markers(text: str) -> str:
    cleaned = re.sub(r"^!\[[^\]]*\]\(_theme/(?:cover\.jpg|divider\.png|badge\.png|badge-mini\.png)\)\s*$", "", text, flags=re.M)
    for marker in (HEADER_TITLE_LINE, HEADER_SUBTITLE_LINE, FOOTER_LINE):
        cleaned = re.sub(r"^" + re.escape(marker) + r"\s*$", "", cleaned, flags=re.M)
    cleaned = re.sub(
        r"^" + re.escape(HIGHLIGHTS_TITLE_LINE) + r"\s*$[\s\S]*?(?=^# |\Z)",
        "",
        cleaned,
        flags=re.M,
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()



def decorate_markdown_with_theme(markdown_text: str, markdown_path: str) -> str:
    text = _strip_previous_theme_markers(markdown_text or "")
    if not text:
        return markdown_text

    assets = ensure_theme_assets(markdown_path)
    badge = assets.get("badge")
    badge_mini = assets.get("badge_mini")
    parts: List[str] = []

    if badge:
        badge_rel = os.path.relpath(badge, start=os.path.dirname(markdown_path)).replace("\\", "/")
        parts.append(f"![{THEME_BADGE_ALT}]({badge_rel})")
        parts.append("")

    parts.append(HEADER_SUBTITLE_LINE)
    parts.append("")
    # 报头不再放「万有预报」大标题（推送标题里已经有了），改成当期速递
    parts.append(HIGHLIGHTS_TITLE_LINE)
    parts.append("")
    for bullet in _build_highlights(text):
        parts.append(f"- {bullet}")
    parts.append("")
    parts.append(text)
    parts.append("")

    if badge_mini:
        badge_mini_rel = os.path.relpath(badge_mini, start=os.path.dirname(markdown_path)).replace("\\", "/")
        parts.append(f"![{THEME_BADGE_MINI_ALT}]({badge_mini_rel})")
    parts.append(FOOTER_LINE)
    return "\n".join(part for part in parts if part is not None).strip() + "\n"



def _resolve_image_src(src: str, markdown_path: str, output_path: str) -> str:
    cleaned = src.strip().strip("<>").strip('"').strip("'")
    if not cleaned:
        return cleaned
    if is_remote_or_data_image(cleaned):
        return cleaned

    markdown_dir = os.path.dirname(markdown_path)
    resolved_path = resolve_existing_image_path(cleaned, base_dir=markdown_dir)
    if resolved_path is not None:
        resolved = str(resolved_path)
    else:
        resolved = os.path.normpath(os.path.join(markdown_dir, clean_markdown_image_target(cleaned)))
    relative = os.path.relpath(resolved, start=os.path.dirname(output_path))
    return relative.replace("\\", "/")



def _should_skip_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped.startswith("[English]("):
        return True
    if stripped.startswith("* [") and "](" in stripped:
        return True
    return False



def _split_label_value(text: str) -> Tuple[str, str]:
    match = re.match(r"^([^:：]{1,12})[:：]\s*(.+)$", text)
    if not match:
        return "", text
    return match.group(1).strip(), match.group(2).strip()



def _strip_markdown_emphasis(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("**") and stripped.endswith("**") and len(stripped) > 4:
        return stripped[2:-2].strip()
    if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 2:
        return stripped[1:-1].strip()
    return stripped


def _is_table_row(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _is_table_separator(text: str) -> bool:
    return bool(re.match(r"^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$", text.strip()))


def _split_table_row(text: str) -> List[str]:
    stripped = text.strip().strip("|")
    cells = re.split(r"(?<!\\)\|", stripped)
    return [cell.replace(r"\|", "|").strip() for cell in cells]


def _render_markdown_table(table_lines: List[str]) -> str:
    rows = [line for line in table_lines if _is_table_row(line) and not _is_table_separator(line)]
    if not rows:
        return ""
    parsed = [_split_table_row(line) for line in rows]
    max_cols = max(len(row) for row in parsed)
    for row in parsed:
        row.extend([""] * (max_cols - len(row)))
    header = parsed[0]
    body = parsed[1:]
    head_html = "".join(f"<th>{html.escape(cell)}</th>" for cell in header)
    body_html = "\n".join(
        "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
        for row in body
    )
    return (
        "<div class='table-wrap'><table class='info-table'>"
        f"<thead><tr>{head_html}</tr></thead>"
        f"<tbody>{body_html}</tbody>"
        "</table></div>"
    )


def _is_time_like_label(label: str) -> bool:
    return label in {
        "日期",
        "时间",
        "发布日期",
        "报告时间",
        "截止时间",
        "截止日期",
        "活动时间",
        "演出时间",
        "开票时间",
    }


def _highlight_time_text(text: str) -> str:
    # 规则表在 generators/text_spans.py，和秀米内联那条链路共用一份。
    return highlight_time_spans(html.escape(text or ""))


# ── 一键复制到秀米 / 公众号 ─────────────────────────────────────────────────
# 公众号和秀米只认内联 style，所以复制源直接用 wechat_inline 产出的那份内联
# HTML —— 和手工粘进编辑器的是同一份，保证「所复即所粘」。页面本体仍是带 class
# 的 H5，两者由同一份 Markdown 生成、共用同一套设计语言。

_COPY_CSS = """
    .copy-bar { position: fixed; right: 16px; bottom: 16px; z-index: 9999; display: flex; align-items: center; gap: 10px; }
    .copy-bar button { appearance: none; border: 1px solid var(--accent-deep); background: var(--accent); color: #4a3800; font-family: inherit; font-weight: 700; font-size: 14px; padding: 10px 18px; border-radius: 999px; cursor: pointer; box-shadow: 0 8px 20px rgba(120, 90, 20, 0.25); }
    .copy-bar button:hover:not(:disabled) { background: var(--accent-deep); color: #fff; }
    .copy-bar button:active:not(:disabled) { transform: translateY(1px); }
    .copy-bar button:disabled { opacity: 0.6; cursor: default; }
    .copy-status { font-size: 13px; color: var(--muted); background: rgba(255, 255, 255, 0.94); border: 1px solid rgba(213, 165, 28, 0.35); border-radius: 999px; padding: 5px 10px; max-width: 48vw; }
    /* 手机上窗口只有 390px，那行提示会压住正文；窄屏只留按钮，反馈改成按钮文案 */
    @media (max-width: 640px) { .copy-status { display: none; } }
    /* 复制源必须能被选区命中：不能用 display:none，挪到屏幕外即可 */
    #wx-copy-src { position: fixed; left: -10000px; top: 0; width: 390px; }
    @media print { .copy-bar { display: none; } }
"""

_COPY_BLOCK = """
  <div class="copy-bar">
    <span class="copy-status" id="wx-copy-status">复制后可直接粘贴到秀米 / 公众号草稿</span>
    <button type="button" id="wx-copy-btn">复制到公众号</button>
  </div>
  <div id="wx-copy-src" aria-hidden="true">__COPY_SOURCE__</div>
  <script>
  (function () {
    var btn = document.getElementById('wx-copy-btn');
    var status = document.getElementById('wx-copy-status');
    var src = document.getElementById('wx-copy-src');
    if (!btn || !src) return;
    var idle = status ? status.textContent : '';

    function say(text, tone) {
      if (!status) return;
      status.textContent = text;
      status.style.color = tone === 'ok' ? '#2f6b2f' : (tone === 'err' ? '#b3352a' : '');
      if (tone) {
        window.setTimeout(function () {
          status.textContent = idle;
          status.style.color = '';
        }, 5000);
      }
    }

    function copyBySelection() {
      var range = document.createRange();
      range.selectNodeContents(src);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      sel.removeAllRanges();
      return ok;
    }

    /* 本地图片（E:/… 或 file://）粘到公众号后是断图，如实告诉用户要补传 */
    function localImageCount() {
      var imgs = src.querySelectorAll('img');
      var n = 0;
      for (var i = 0; i < imgs.length; i++) {
        var s = imgs[i].getAttribute('src') || '';
        if (/^(file:|[A-Za-z]:)/.test(s)) n++;
      }
      return n;
    }

    function doneMessage(ok) {
      if (!ok) return '复制失败，请手动全选复制';
      var n = localImageCount();
      return n > 0
        ? '已复制；有 ' + n + ' 张本地图片需在编辑器里重新上传'
        : '已复制，去编辑器里粘贴';
    }

    function copyRich() {
      var markup = src.innerHTML;
      var plain = src.innerText || src.textContent || '';
      if (window.isSecureContext && navigator.clipboard && window.ClipboardItem) {
        return navigator.clipboard.write([new ClipboardItem({
          'text/html': new Blob([markup], { type: 'text/html' }),
          'text/plain': new Blob([plain], { type: 'text/plain' })
        })]).then(function () { return true; }, function () { return copyBySelection(); });
      }
      return Promise.resolve(copyBySelection());
    }

    btn.addEventListener('click', function () {
      btn.disabled = true;
      copyRich().then(function (ok) {
        btn.disabled = false;
        say(doneMessage(ok), ok ? 'ok' : 'err');
        // 窄屏没有状态行，直接把结果写在按钮上
        var original = btn.textContent;
        btn.textContent = ok ? '已复制' : '复制失败';
        window.setTimeout(function () { btn.textContent = original; }, 2000);
      });
    });
  })();
  </script>
"""


def build_copy_block(copy_source_html: str) -> str:
    """把内联正文塞进隐藏容器，配好按钮和复制脚本。"""

    return _COPY_BLOCK.replace("__COPY_SOURCE__", copy_source_html or "")


def markdown_to_h5_html(
    markdown_text: str,
    markdown_path: str,
    output_path: str,
    title: str = "",
    copy_source_html: str = "",
    hero_badge_src: str = "",
    hero_meta: str = "",
) -> str:
    page_title = _safe_title(title)
    theme_assets = ensure_theme_assets(output_path)
    badge_rel = ""
    badge_mini_rel = ""
    if theme_assets.get("badge"):
        badge_rel = os.path.relpath(theme_assets["badge"], start=os.path.dirname(output_path)).replace("\\", "/")
    if theme_assets.get("badge_mini"):
        badge_mini_rel = os.path.relpath(theme_assets["badge_mini"], start=os.path.dirname(output_path)).replace("\\", "/")

    blocks: List[str] = []
    article_open = False
    section_open = False
    highlights_open = False

    def close_article():
        nonlocal article_open
        if article_open:
            blocks.append("</article>")
            article_open = False

    def close_section():
        nonlocal section_open, highlights_open
        if section_open:
            close_article()
            if highlights_open:
                blocks.append("</div>")  # .highlights-box
                highlights_open = False
            blocks.append("</section>")
            section_open = False

    lines = markdown_text.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped = _maybe_fix_mojibake(raw_line)
        if _is_table_row(stripped) and index + 1 < len(lines) and _is_table_separator(_maybe_fix_mojibake(lines[index + 1])):
            table_lines = [stripped, _maybe_fix_mojibake(lines[index + 1])]
            index += 2
            while index < len(lines) and _is_table_row(_maybe_fix_mojibake(lines[index])):
                table_lines.append(_maybe_fix_mojibake(lines[index]))
                index += 1
            rendered_table = _render_markdown_table(table_lines)
            if rendered_table:
                blocks.append(rendered_table)
            continue
        if _is_table_row(stripped):
            lookahead = index + 1
            while lookahead < len(lines) and not _maybe_fix_mojibake(lines[lookahead]).strip():
                lookahead += 1
            if lookahead < len(lines) and _is_table_separator(_maybe_fix_mojibake(lines[lookahead])):
                table_lines = [stripped, _maybe_fix_mojibake(lines[lookahead])]
                index = lookahead + 1
                while index < len(lines):
                    candidate = _maybe_fix_mojibake(lines[index])
                    if not candidate.strip():
                        index += 1
                        continue
                    if not _is_table_row(candidate):
                        break
                    table_lines.append(candidate)
                    index += 1
                rendered_table = _render_markdown_table(table_lines)
                if rendered_table:
                    blocks.append(rendered_table)
                continue
        index += 1
        if _should_skip_line(stripped):
            continue

        image_match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if image_match:
            alt = _maybe_fix_mojibake(image_match.group(1).strip())
            src = html.escape(_resolve_image_src(image_match.group(2), markdown_path, output_path))
            if alt in {THEME_BADGE_ALT, THEME_BADGE_MINI_ALT}:
                continue
            blocks.append(f"<figure class='figure'><img src='{src}' alt='{html.escape(alt or '配图')}' loading='lazy' /></figure>")
            continue

        if stripped in {HEADER_TITLE_LINE, HEADER_SUBTITLE_LINE, FOOTER_LINE}:
            continue

        if stripped.startswith("# "):
            close_section()
            current_section = stripped[2:].strip()
            # 栏目导语已去掉：硬编码的导语每期重复、和卡片内容重复，且常与当期事实
            # 矛盾（十月还写「天气渐暖」）。栏目头保留 kicker + 标题即可。
            is_highlights = current_section == HIGHLIGHTS_SECTION_TITLE
            blocks.append("<section class='section highlights'>" if is_highlights else "<section class='section'>")
            blocks.append("<div class='section-head'>")
            blocks.append("<span class='section-kicker'>本期栏目</span>")
            blocks.append(f"<h2>{html.escape(current_section)}</h2>")
            blocks.append("</div>")
            section_open = True
            if is_highlights:
                # 速递整段套一个和卡片同款的文本框，读起来不再是一串裸列表
                blocks.append("<div class='highlights-box'>")
                highlights_open = True
            continue

        if stripped.startswith("## "):
            close_article()
            blocks.append("<article class='card'>")
            blocks.append("<div class='card-notch'></div>")
            blocks.append(f"<h3>{html.escape(stripped[3:].strip())}</h3>")
            article_open = True
            continue

        if stripped.startswith("### "):
            blocks.append(f"<h4 class='subhead'>{html.escape(stripped[4:].strip())}</h4>")
            continue

        label, value = _split_label_value(stripped)
        if label == "要点透视":
            blocks.append(
                "<div class='lede-box'>"
                "<div class='lede-tag'>要点透视</div>"
                f"<p>{_highlight_time_text(value)}</p>"
                "</div>"
            )
            continue
        if label in META_LABELS:
            rendered_value = _highlight_time_text(value) if _is_time_like_label(label) else html.escape(value)
            if label == "链接" and re.match(r"^https?://", value):
                rendered_value = f"<a href='{html.escape(value)}'>{html.escape(value)}</a>"
            value_class = "meta-value"
            if label in {"日期", "时间", "发布日期", "报告时间"}:
                value_class += " is-highlight"
            blocks.append(
                f"<p class='meta-row'><span class='meta-label'>{html.escape(label)}</span><span class='{value_class}'>{rendered_value}</span></p>"
            )
            continue

        if re.match(r"^https?://", stripped):
            url = html.escape(stripped)
            blocks.append(f"<p class='link-row'><a href='{url}'>{url}</a></p>")
            continue

        if stripped.startswith(("- ", "• ")):
            bullet_text = stripped[2:].strip()
            blocks.append(f"<p class='bullet'>{_highlight_time_text(bullet_text)}</p>")
            continue

        emphasis_text = _strip_markdown_emphasis(stripped)
        if emphasis_text != stripped:
            blocks.append(f"<p class='note'><strong>{html.escape(emphasis_text)}</strong></p>")
            continue

        if stripped.startswith("*"):
            blocks.append(f"<p class='note'>{html.escape(stripped.lstrip('*').strip())}</p>")
            continue

        blocks.append(f"<p>{_highlight_time_text(stripped)}</p>")

    close_section()
    body_html = "\n".join(blocks)

    hero_badge = ""
    if badge_rel:
        hero_badge = f"<img class='hero-badge' src='{html.escape(badge_rel)}' alt='物理系风格标识' loading='lazy' />"
    hero_banner = ""
    if hero_badge_src:
        hero_banner = (
            f"<img class='hero-banner' src='{html.escape(hero_badge_src)}' "
            "alt='万有预报' loading='lazy' />"
        )
    hero_meta_html = f"<p class='hero-meta'>{html.escape(hero_meta)}</p>" if hero_meta else ""
    footer_badge = ""
    if badge_mini_rel:
        footer_badge = f"<img class='footer-badge' src='{html.escape(badge_mini_rel)}' alt='物理系风格标识' loading='lazy' />"

    # 只有拿到内联正文才挂复制按钮；没有就不往页面里塞死代码
    copy_css = _COPY_CSS if copy_source_html else ""
    copy_block = build_copy_block(copy_source_html) if copy_source_html else ""

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(page_title)}</title>
  <style>
    :root {{
      --accent: #f5c833;
      --accent-deep: #d5a51c;
      --accent-soft: rgba(245, 200, 51, 0.16);
      --accent-ink: #8f6a00;
      --paper: #ffffff;
      --paper-soft: #faf7ef;
      --ink: #3e3e3e;
      --muted: #70695d;
      --line: rgba(213, 165, 28, 0.55);
      --bg: #f6f2e8;
      --shadow: 0 22px 50px rgba(92, 74, 16, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    /* 卡片右下角的折角（.card-notch）是故意探出去的装饰，手机上会多出 9px 横向滚动；
       overflow-x 要同时放在 html 上，光放 body 挡不住 documentElement.scrollWidth。 */
    html {{ overflow-x: hidden; }}
    body {{
      margin: 0;
      overflow-x: hidden;
      background:
        radial-gradient(circle at top right, rgba(245, 200, 51, 0.12), transparent 24%),
        radial-gradient(circle at left 20%, rgba(171, 211, 224, 0.18), transparent 18%),
        var(--bg);
      color: var(--ink);
      font-family: "Source Han Serif SC", "Noto Serif SC", "Songti SC", serif;
    }}
    .page {{
      width: min(760px, calc(100vw - 24px));
      margin: 0 auto;
      padding: 22px 0 46px;
    }}
    .hero {{
      position: relative;
      overflow: hidden;
      background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(250,247,239,0.96));
      border: 1px solid var(--line);
      border-radius: 26px;
      padding: 22px 20px 20px;
      box-shadow: var(--shadow);
    }}
    .hero::before {{
      content: "";
      position: absolute;
      left: 20px;
      right: 20px;
      top: 0;
      height: 5px;
      border-radius: 999px;
      background: var(--accent);
    }}
    .hero-top {{ display: flex; align-items: center; gap: 14px; margin-bottom: 12px; }}
    .hero-banner {{ display: block; width: 100%; max-width: 100%; height: auto; margin: 16px 0 0; border-radius: 14px; }}
    .hero-badge {{ width: 68px; height: 68px; border-radius: 50%; flex: 0 0 auto; box-shadow: 0 10px 24px rgba(143, 106, 0, 0.12); background: #fff; }}
    .hero-mark {{ display: inline-flex; align-items: center; gap: 8px; padding: 5px 10px; border-radius: 999px; background: var(--accent-soft); color: var(--accent-ink); font-size: 12px; letter-spacing: 0.08em; }}
    .hero h1 {{ margin: 8px 0 0; font-size: 34px; line-height: 1.15; letter-spacing: 0.03em; }}
    .hero p {{ margin: 10px 0 0; color: var(--muted); line-height: 1.85; font-size: 15px; }}
    .hero .hero-meta {{ margin: 10px 0 0; color: var(--muted); font-size: 14px; line-height: 1.8; letter-spacing: 0.01em; }}
    .section {{ margin-top: 24px; }}
    .section-head {{ margin-bottom: 10px; }}
    .section-kicker {{ display: inline-block; margin-bottom: 8px; padding: 0.45em 0.8em; background: rgba(245, 200, 51, 0.7); color: #fff; font-size: 16px; letter-spacing: 0.08em; border-radius: 4px 0 0 4px; position: relative; }}
    .section-kicker::after {{ content: ""; position: absolute; top: 0; right: -18px; border-left: 18px solid rgba(245, 200, 51, 0.7); border-top: 16px solid transparent; border-bottom: 16px solid transparent; }}
    .section h2 {{ margin: 4px 0 0; font-size: 28px; line-height: 1.2; }}
    .section-lead {{ margin: 8px 0 0; color: var(--muted); font-size: 15px; line-height: 1.8; }}
    .card {{ position: relative; margin: 14px 0 0; padding: 16px 16px 14px; background: var(--paper); border: 1px solid var(--line); box-shadow: 0 10px 24px rgba(92, 74, 16, 0.05); }}    .card + .card {{ margin-top: 12px; }}
    .card-notch {{ position: absolute; right: -1px; bottom: -1px; width: 22px; height: 22px; border-right: 1px solid var(--line); border-bottom: 1px solid var(--line); transform: rotate(-45deg) translate(9px, 9px); background: var(--paper); transform-origin: center; }}
    .card h3 {{ margin: 0 0 10px; font-size: 22px; line-height: 1.5; }}
    .subhead {{ margin: 14px 0 6px; font-size: 16px; color: var(--accent-ink); border-left: 4px solid rgba(171, 211, 224, 0.95); padding-left: 8px; }}
    p {{ margin: 8px 0; line-height: 1.9; font-size: 15px; word-break: break-word; }}
    .lede-box {{ margin: 10px 0 14px; border-top: 5px solid var(--accent); border-right: 5px solid var(--accent); background: rgba(245, 200, 51, 0.16); padding: 10px 12px 10px 14px; }}
    .lede-tag {{ display: inline-block; margin-bottom: 6px; padding: 3px 9px; background: rgba(245, 200, 51, 0.75); color: #fff; font-size: 14px; letter-spacing: 0.08em; }}
    .lede-box p {{ margin: 0; }}
    .meta-row {{ display: flex; gap: 10px; align-items: baseline; margin: 7px 0; }}
    .meta-label {{ flex: 0 0 auto; min-width: 78px; color: var(--muted); font-size: 13px; letter-spacing: 0.04em; }}
    .meta-value {{ flex: 1 1 auto; }}
    .meta-value.is-highlight, .time-highlight {{ color: #f96e57; font-weight: 700; }}
    .note {{ color: var(--ink); font-size: 14px; }}
    .bullet {{ position: relative; padding-left: 1.1em; }}
    .bullet::before {{ content: "•"; position: absolute; left: 0; color: var(--accent-ink); }}
    /* 「本期要点速递」整段套一个和卡片同款的圆角文本框 */
    .highlights-box {{ margin: 12px 0 4px; padding: 14px 18px 16px; background: var(--paper); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 10px 24px rgba(92, 74, 16, 0.05); }}
    .highlights-box .bullet {{ margin: 7px 0; line-height: 1.85; }}
    .table-wrap {{ margin: 12px 0; overflow-x: auto; border: 1px solid rgba(213, 165, 28, 0.45); border-radius: 8px; background: #fffdf6; }}
    .info-table {{ width: 100%; border-collapse: collapse; min-width: 420px; font-size: 14px; line-height: 1.65; }}
    .info-table th, .info-table td {{ padding: 8px 10px; border-bottom: 1px solid rgba(213, 165, 28, 0.26); border-right: 1px solid rgba(213, 165, 28, 0.18); text-align: left; vertical-align: top; }}
    .info-table th {{ background: rgba(245, 200, 51, 0.18); color: var(--accent-ink); font-weight: 700; }}
    .info-table tr:last-child td {{ border-bottom: 0; }}
    .info-table th:last-child, .info-table td:last-child {{ border-right: 0; }}
    a {{ color: #8b5600; text-decoration: none; border-bottom: 1px solid rgba(139, 86, 0, 0.24); }}
    .figure {{ margin: 12px 0 4px; text-align: center; }}
    .figure img {{ display: inline-block; max-width: 100%; border-radius: 10px; border: 1px solid rgba(62, 62, 62, 0.08); }}
    .page-footer {{ margin-top: 28px; padding: 16px 14px 0; text-align: center; }}
    .footer-note {{ margin-top: 12px; border-top: 4px solid var(--accent); background: #efefef; padding: 12px 14px; border-radius: 0 0 16px 16px; font-size: 14px; color: var(--muted); line-height: 1.8; }}
    .footer-badge {{ width: 54px; height: 54px; border-radius: 50%; box-shadow: 0 10px 20px rgba(143, 106, 0, 0.10); background: #fff; }}
    @media (max-width: 640px) {{
      .page {{ width: min(100vw - 16px, 760px); padding-top: 14px; }}
      .hero {{ padding: 18px 14px 16px; border-radius: 22px; }}
      .hero-top {{ gap: 10px; }}
      .hero-badge {{ width: 56px; height: 56px; }}
      .hero h1 {{ font-size: 28px; }}
      .section-kicker {{ font-size: 14px; }}
      .section-kicker::after {{ right: -16px; border-left-width: 16px; border-top-width: 15px; border-bottom-width: 15px; }}
      .section h2 {{ font-size: 24px; }}
      .card h3 {{ font-size: 19px; }}
      .meta-row {{ display: block; }}
      .meta-label {{ display: block; min-width: 0; margin-bottom: 2px; }}
    }}
    {copy_css}
  </style>
</head>
<body>
  <main class="page">
    <header class="hero">
      <h1>{html.escape(page_title)}</h1>
      {hero_meta_html}
      {hero_banner}
    </header>
    {body_html}
    <footer class="page-footer">
      {footer_badge}
      <div class="footer-note">本期万有预报到这里就结束了。<br />万有预报，下期再见。</div>
    </footer>
  </main>
  {copy_block}
</body>
</html>
'''



HERO_BADGE_FILENAME = "badge.jpg"


def hero_badge_source() -> str:
    """页头横幅图的绝对路径（仓库根目录的 ``badge.jpg``）。

    没有就返回空串、页头只留标题和元信息——不再回退别的文件名。
    """

    root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    path = os.path.join(root, HERO_BADGE_FILENAME)
    return path.replace("\\", "/") if os.path.isfile(path) else ""


def export_h5(markdown_path: str, output_path: str, title: str = "") -> str:
    with open(markdown_path, "r", encoding="utf-8") as f:
        markdown_text = f.read()

    # 延迟导入：wechat_inline 依赖本模块的常量，模块级导入会成环
    from generators.wechat_inline import markdown_to_wechat_inline_html
    from wanyou import academic_calendar

    # 页头元信息：生成时间 +（实时从 info 抓到才算）校历周次
    hero_meta = academic_calendar.summary_line()
    hero_badge_src = hero_badge_source()

    copy_source_html = markdown_to_wechat_inline_html(
        markdown_text,
        markdown_path=markdown_path,
        hero_badge_src=hero_badge_src,
        hero_meta=hero_meta,
    )
    # 本地图片在粘贴时必然是断图，导出阶段就压成 data: 内嵌，让复制真正做到
    # 「不用上传」。压不动的（超大/读失败）保持原样，页面按钮会如实提示张数。
    copy_source_html, image_stats = embed_local_images(
        copy_source_html,
        base_dir=os.path.dirname(os.path.abspath(markdown_path)),
    )
    remaining = int(image_stats.get("remaining_local") or 0)
    if remaining:
        # 早期预警：别等到用户在编辑器里发现断图
        print(
            f"[copy] {remaining} 张本地图片没能内嵌（超出预算或读取失败），"
            "粘贴到公众号/秀米后需要手动补图"
        )
    html_text = markdown_to_h5_html(
        markdown_text,
        markdown_path=markdown_path,
        output_path=output_path,
        title=title,
        copy_source_html=copy_source_html,
        hero_badge_src=hero_badge_src,
        hero_meta=hero_meta,
    )
    # 页面本体也要自包含：<img> 默认写的是相对输出目录的路径，把 HTML 单独拷贝到
    # 别处（发给自己、塞进共享盘、丢掉 output/ 目录）就会整页断图。这里把页面里的
    # 本地 <img> 同样压成 data:，最终产物是单文件、双击即可看。复制源里的 data:
    # 会被跳过，不会重复嵌入。
    html_text, page_image_stats = embed_local_images(
        html_text,
        base_dir=os.path.dirname(os.path.abspath(output_path)),
    )
    page_remaining = int(page_image_stats.get("remaining_local") or 0)
    if page_remaining:
        print(
            f"[page] {page_remaining} 张本地图片没能内嵌（超出预算或读取失败），"
            "HTML 单独移动后这些图片会找不到"
        )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_text)
    return output_path
