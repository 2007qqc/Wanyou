import html
import os
import re
from typing import List, Tuple

from generators.h5_generator import FOOTER_LINE, HEADER_SUBTITLE_LINE, HEADER_TITLE_LINE
from generators.text_spans import INLINE_TIME_SPAN, highlight_time_spans
from wanyou.image_paths import clean_markdown_image_target, is_remote_or_data_image, resolve_existing_image_path

THEME_BADGE_ALTS = {"物理系风格标识", "物理系风格标识-页尾"}
TIME_LABELS = {"日期", "时间", "发布日期", "报告时间", "截止时间", "活动时间", "演出时间", "开票时间"}
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
    "截止时间",
    "活动时间",
}

<<<<<<< HEAD
PAGE_TITLE = "万有预报"

# ── 尺寸与配色，取自 h5_generator 的 CSS 变量，保证两份产物是同一套视觉 ──
ACCENT = "#f5c833"
ACCENT_SOFT = "rgba(245,200,51,0.16)"
ACCENT_INK = "#8f6a00"
ACCENT_LINE = "rgba(213,165,28,0.55)"
INK = "#3e3e3e"
MUTED = "#70695d"
# 公众号深色模式只对「纯白」这类元素单独做反转，页面底色和卡片底色一旦亮度
# 不同，就会出现「卡片黑了、外面还是浅的」的割裂。把两者统一成同一个纯白，
# 微信要么整体不动、要么整体反转，内外永远一致。
# 代价：浅色模式下正文是纯白而不是 H5 的米色纸感。
PAPER = "#ffffff"
PAGE_BG = "#ffffff"
# 字体名必须用单引号：这份样式最终会写进 style="…" 属性里，
# 用双引号会把属性提前截断（font-family 整条失效，只是 Windows 默认中文
# 字体恰好是宋体，才看起来"像是生效了"）。
SERIF = "'Source Han Serif SC','Noto Serif SC','Songti SC',serif"

PAGE_STYLE = (
    # box-sizing 必须写：默认 content-box 时 max-width 不含内边距，
    # 390 的视口会被撑成 390+24=414，右侧整片内容被裁。
    f"box-sizing:border-box;max-width:760px;margin:0 auto;padding:8px 12px 24px;background:{PAGE_BG};color:{INK};"
    f"font-family:{SERIF};line-height:1.75;font-size:15px;word-break:break-word;overflow-wrap:break-word;"
    # 卡片右下折角会探出边距，H5 靠 body{overflow-x:hidden} 兜底，这里给同样的兜底
    "overflow:hidden;"
)
# H5 的顶部黄条是 .hero::before 伪元素，公众号里没有伪元素，用一条真实的分隔条替代
HERO_BAR_STYLE = f"height:5px;margin:0 0 16px;border-radius:999px;background:{ACCENT};"
HERO_STYLE = (
    f"margin:0 0 18px;padding:22px 20px 20px;border:1px solid {ACCENT_LINE};border-radius:26px;"
    # 原来是从纯白到米白的渐变；公众号深色模式会把"纯白"和"米白"区别对待，
    # 所以这里也统一成强调色淡染，全文只剩「纯白 + 黄调」两类底色。
    "background:rgba(245,200,51,0.07);"
    "box-shadow:0 22px 50px rgba(92,74,16,0.08);"
)
HERO_MARK_STYLE = (
    f"display:inline-block;margin:0 0 10px;padding:5px 10px;border-radius:999px;"
    f"background:{ACCENT_SOFT};color:{ACCENT_INK};font-size:12px;letter-spacing:.08em;"
)
H1_STYLE = f"margin:8px 0 0;color:{INK};font-size:34px;font-weight:700;line-height:1.15;letter-spacing:.03em;"
SUBTITLE_STYLE = f"margin:10px 0 0;color:{MUTED};font-size:15px;line-height:1.85;"
HERO_BANNER_STYLE = (
    "display:block;width:100%;max-width:100%;height:auto;margin:16px 0 0;border-radius:14px;"
)
HERO_META_STYLE = f"margin:10px 0 0;color:{MUTED};font-size:14px;line-height:1.8;"

SECTION_STYLE = "margin:24px 0 0;padding:0;"
# H5 的 kicker 是「药丸 + ::after 三角」；这里用「药丸 span + border 三角 span」拼同样的形状
SECTION_TAG_STYLE = (
    "display:inline-block;margin:0 0 8px;padding:.45em .8em;background:rgba(245,200,51,0.7);"
    "color:#fff;font-size:16px;letter-spacing:.08em;border-radius:4px 0 0 4px;vertical-align:middle;"
)
SECTION_TAG_ARROW_STYLE = (
    "display:inline-block;width:0;height:0;margin:0 0 8px;"
    "border-left:18px solid rgba(245,200,51,0.7);"
    "border-top:16px solid transparent;border-bottom:16px solid transparent;vertical-align:middle;"
)
SECTION_TITLE_STYLE = f"margin:4px 0 0;color:{INK};font-size:28px;font-weight:700;line-height:1.2;"
SECTION_LEAD_STYLE = f"margin:8px 0 0;color:{MUTED};font-size:15px;line-height:1.8;"

CARD_STYLE = (
    f"position:relative;margin:14px 0 0;padding:16px 16px 14px;background:{PAPER};"
    f"border:1px solid {ACCENT_LINE};box-shadow:0 10px 24px rgba(92,74,16,0.05);"
)
CARD_NOTCH_STYLE = (
    "position:absolute;right:-1px;bottom:-1px;width:22px;height:22px;"
    f"border-right:1px solid {ACCENT_LINE};border-bottom:1px solid {ACCENT_LINE};"
    f"background:{PAPER};transform:rotate(-45deg) translate(9px,9px);"
)
CARD_TITLE_STYLE = f"margin:0 0 10px;color:{INK};font-size:22px;font-weight:700;line-height:1.5;"
SUBHEAD_STYLE = (
    f"margin:14px 0 6px;color:{ACCENT_INK};font-size:16px;font-weight:700;line-height:1.7;"
    "border-left:4px solid rgba(171,211,224,0.95);padding-left:8px;"
)
PARA_STYLE = f"margin:8px 0;color:{INK};font-size:15px;line-height:1.9;"
LEDE_STYLE = (
    f"margin:10px 0 14px;border-top:5px solid {ACCENT};border-right:5px solid {ACCENT};"
    f"background:{ACCENT_SOFT};padding:10px 12px 10px 14px;"
)
LEDE_TAG_STYLE = (
    "display:inline-block;margin:0 0 6px;padding:3px 9px;background:rgba(245,200,51,0.75);"
    "color:#fff;font-size:14px;letter-spacing:.08em;"
)
LEDE_TEXT_STYLE = f"margin:0;color:{INK};font-size:15px;line-height:1.9;"
# 字段行对齐 H5 在手机上的表现：标签独占一行，取值在下一行（@media max-width:640px）
META_ROW_STYLE = f"margin:7px 0;color:{INK};font-size:15px;line-height:1.75;word-break:break-word;overflow-wrap:anywhere;"
META_LABEL_STYLE = f"display:block;margin:0 0 2px;color:{MUTED};font-size:13px;letter-spacing:.04em;"
=======
PAGE_STYLE = "margin:0 auto;padding:0 0 8px;background:#fffaf0;color:#3d3525;font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue','PingFang SC','Microsoft YaHei',sans-serif;line-height:1.75;font-size:15px;"
HERO_STYLE = "margin:0 0 18px;padding:22px 18px 20px;border:1px solid #ead9a8;background:#fff3c4;border-radius:12px;"
HERO_MARK_STYLE = "display:inline-block;margin-bottom:8px;padding:3px 8px;background:#f96e57;color:#fff;border-radius:999px;font-size:12px;letter-spacing:.08em;"
H1_STYLE = "margin:0;color:#312714;font-size:26px;font-weight:800;line-height:1.25;"
SUBTITLE_STYLE = "margin:8px 0 0;color:#7a6a45;font-size:14px;"
SECTION_STYLE = "margin:22px 0 0;padding:0;"
SECTION_TAG_STYLE = "display:inline-block;margin:0 0 8px;padding:4px 10px;background:#f5c833;color:#fff;border-radius:4px;font-size:13px;letter-spacing:.08em;"
SECTION_TITLE_STYLE = "margin:0;color:#312714;font-size:22px;font-weight:800;line-height:1.35;"
SECTION_LEAD_STYLE = "margin:8px 0 10px;color:#7d704d;font-size:14px;line-height:1.7;"
CARD_STYLE = "margin:12px 0 0;padding:15px 14px;background:#fffdf6;border:1px solid #ecdcae;border-radius:10px;box-shadow:0 4px 14px rgba(120,90,20,.06);"
CARD_TITLE_STYLE = "margin:0 0 10px;color:#322714;font-size:18px;font-weight:700;line-height:1.45;"
PARA_STYLE = "margin:8px 0;color:#443929;font-size:15px;line-height:1.75;"
LEDE_STYLE = "margin:10px 0;padding:10px 12px;background:#fff0df;border-left:4px solid #f96e57;border-radius:6px;"
LEDE_TAG_STYLE = "margin:0 0 4px;color:#f96e57;font-size:13px;font-weight:700;"
META_ROW_STYLE = "margin:5px 0;color:#4f432f;font-size:14px;line-height:1.65;"
META_LABEL_STYLE = "display:inline-block;margin-right:6px;color:#8f7a49;font-weight:700;"
>>>>>>> 319500b94447db31f5ff354bce92613fd8c603cb
TIME_VALUE_STYLE = "color:#f96e57;font-weight:700;"
LINK_STYLE = "color:#2f6f9f;text-decoration:underline;word-break:break-all;"
BULLET_STYLE = "margin:6px 0 6px 1em;color:#443929;font-size:15px;line-height:1.7;"
IMAGE_STYLE = "display:block;width:100%;max-width:100%;height:auto;margin:10px auto;border-radius:8px;"
FOOTER_STYLE = "margin:24px 0 0;padding:14px 10px;text-align:center;color:#8a7c58;font-size:14px;"
TABLE_WRAP_STYLE = "margin:10px 0;overflow-x:auto;border:1px solid #ecdcae;border-radius:8px;background:#fffdf6;"
TABLE_STYLE = "width:100%;border-collapse:collapse;font-size:14px;line-height:1.6;"
TH_STYLE = "padding:7px 8px;border:1px solid #ecdcae;background:#fff0bf;color:#6f5716;font-weight:700;text-align:left;vertical-align:top;"
TD_STYLE = "padding:7px 8px;border:1px solid #ecdcae;color:#443929;text-align:left;vertical-align:top;"


def _split_label_value(text: str) -> Tuple[str, str]:
    match = re.match(r"^([^:：]{1,12})[:：]\s*(.+)$", text)
    if not match:
        return "", text
    return match.group(1).strip(), match.group(2).strip()


def _strip_emphasis(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("**") and stripped.endswith("**") and len(stripped) > 4:
        return stripped[2:-2].strip()
    if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 2:
        return stripped[1:-1].strip()
    return stripped


def _resolve_image_src(src: str, markdown_path: str) -> str:
    cleaned = src.strip().strip("<>").strip('"').strip("'")
    if not cleaned or is_remote_or_data_image(cleaned):
        return cleaned

    markdown_dir = os.path.dirname(markdown_path)
    resolved_path = resolve_existing_image_path(cleaned, base_dir=markdown_dir)
    if resolved_path is not None:
        resolved = str(resolved_path)
    else:
        resolved = os.path.normpath(os.path.join(markdown_dir, clean_markdown_image_target(cleaned)))
    return resolved.replace("\\", "/")


def _render_text(value: str) -> str:
    # 先转义再标红：TIME_RE 只认中文数字/冒号这类字符，可以安全地作用在转义后的片段上。
    return highlight_time_spans(html.escape(_strip_emphasis(value or "")), opening=INLINE_TIME_SPAN)


def _render_meta(label: str, value: str) -> str:
    escaped_label = html.escape(label)
    if label == "链接" and re.match(r"^https?://", value or ""):
        escaped_url = html.escape(value)
        rendered_value = f"<a href=\"{escaped_url}\" style=\"{LINK_STYLE}\">{escaped_url}</a>"
    else:
        value_style = TIME_VALUE_STYLE if label in TIME_LABELS else "color:#4f432f;"
        rendered_value = f"<span style=\"{value_style}\">{_render_text(value)}</span>"
    return f"<p style=\"{META_ROW_STYLE}\"><span style=\"{META_LABEL_STYLE}\">{escaped_label}</span>{rendered_value}</p>"


def _is_table_row(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _is_table_separator(text: str) -> bool:
    return bool(re.match(r"^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$", text.strip()))


def _split_table_row(text: str) -> List[str]:
    stripped = text.strip().strip("|")
    return [cell.replace(r"\|", "|").strip() for cell in re.split(r"(?<!\\)\|", stripped)]


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
    head = "".join(f"<th style=\"{TH_STYLE}\">{html.escape(cell)}</th>" for cell in header)
    rows_html = "".join(
        "<tr>" + "".join(f"<td style=\"{TD_STYLE}\">{html.escape(cell)}</td>" for cell in row) + "</tr>"
        for row in body
    )
    return f"<section style=\"{TABLE_WRAP_STYLE}\"><table style=\"{TABLE_STYLE}\"><thead><tr>{head}</tr></thead><tbody>{rows_html}</tbody></table></section>"


def markdown_to_wechat_inline_html(
    markdown_text: str,
    markdown_path: str = "",
    *,
    hero_badge_src: str = "",
    hero_meta: str = "",
) -> str:
    blocks: List[str] = [f"<section style=\"{PAGE_STYLE}\">"]
    section_open = False
    card_open = False

    def close_card():
        nonlocal card_open
        if card_open:
            blocks.append("</section>")
            card_open = False

    def close_section():
        nonlocal section_open
        close_card()
        if section_open:
            blocks.append("</section>")
            section_open = False

    def open_section(title: str):
        nonlocal section_open
        close_section()
        # 不再写栏目导语：原来的硬编码导语（「这周和课程、选课、学业节奏直接相关的
        # 更新，先看这里。」）每个栏目每期都一样，既和下面那张卡片重复，又常常和当期
        # 事实对不上。栏目头只说清楚「这是什么栏目」就够了。
        blocks.append(f"<section style=\"{SECTION_STYLE}\">")
        blocks.append(f"<span style=\"{SECTION_TAG_STYLE}\">本期栏目</span>")
        blocks.append(f"<h2 style=\"{SECTION_TITLE_STYLE}\">{html.escape(title)}</h2>")
        section_open = True

    def open_card(title: str):
        nonlocal card_open
        close_card()
        blocks.append(f"<section style=\"{CARD_STYLE}\">")
        blocks.append(f"<h3 style=\"{CARD_TITLE_STYLE}\">{html.escape(title)}</h3>")
        card_open = True

<<<<<<< HEAD
    hero_banner = ""
    if hero_badge_src:
        hero_banner = (
            f"<img src=\"{html.escape(hero_badge_src)}\" alt=\"万有预报\" "
            f"style=\"{HERO_BANNER_STYLE}\" />"
        )
    blocks.append(f"<section style=\"{HERO_BAR_STYLE}\"></section>")
    blocks.append(f"<section style=\"{HERO_STYLE}\">")
    blocks.append(f"<h1 style=\"{H1_STYLE}\">{PAGE_TITLE}</h1>")
    if hero_meta:
        blocks.append(f"<p style=\"{HERO_META_STYLE}\">{html.escape(hero_meta)}</p>")
    if hero_banner:
        blocks.append(hero_banner)
=======
    blocks.append(f"<section style=\"{HERO_STYLE}\">")
    blocks.append(f"<span style=\"{HERO_MARK_STYLE}\">清物语 · 物理系风格</span>")
    blocks.append(f"<p style=\"{SUBTITLE_STYLE}\">清华大学物理系校园信息整理</p>")
>>>>>>> 319500b94447db31f5ff354bce92613fd8c603cb
    blocks.append("</section>")

    lines = (markdown_text or "").splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if _is_table_row(stripped) and index + 1 < len(lines) and _is_table_separator(lines[index + 1].strip()):
            table_lines = [stripped, lines[index + 1].strip()]
            index += 2
            while index < len(lines) and _is_table_row(lines[index].strip()):
                table_lines.append(lines[index].strip())
                index += 1
            rendered_table = _render_markdown_table(table_lines)
            if rendered_table:
                blocks.append(rendered_table)
            continue
        if _is_table_row(stripped):
            lookahead = index + 1
            while lookahead < len(lines) and not lines[lookahead].strip():
                lookahead += 1
            if lookahead < len(lines) and _is_table_separator(lines[lookahead].strip()):
                table_lines = [stripped, lines[lookahead].strip()]
                index = lookahead + 1
                while index < len(lines):
                    candidate = lines[index].strip()
                    if not candidate:
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
        if not stripped:
            continue
        if stripped in {HEADER_TITLE_LINE, HEADER_SUBTITLE_LINE, FOOTER_LINE}:
            continue

        image_match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if image_match:
            alt = image_match.group(1).strip()
            if alt in THEME_BADGE_ALTS:
                continue
            src = html.escape(_resolve_image_src(image_match.group(2), markdown_path), quote=True)
            blocks.append(f"<img src=\"{src}\" alt=\"{html.escape(alt or '配图')}\" style=\"{IMAGE_STYLE}\" />")
            continue

        if stripped.startswith("# "):
            open_section(stripped[2:].strip())
            continue
        if stripped.startswith("## "):
            if not section_open:
                open_section("未分类")
            open_card(stripped[3:].strip())
            continue
        if stripped.startswith("### "):
            blocks.append(f"<p style=\"{PARA_STYLE}font-weight:700;color:#6a5427;\">{html.escape(stripped[4:].strip())}</p>")
            continue

        label, value = _split_label_value(stripped)
        if label == "要点透视":
            # 必须写成「一个 <p> 里用 <br> 分行」，不能写成 <p 红框><p>要点透视</p>
            # <p>正文</p></p>：<p> 不能嵌套 <p>，浏览器会在第一个内层 <p> 处闭合外层的
            # 红框，结果红框变成空框、要点透视的正文整段掉到框外（秀米草稿里就是这个
            # 症状，因为秀米存的是 HTML 片段，渲染时同样按 HTML 规则解析）。
            blocks.append(
                f"<p style=\"{LEDE_STYLE}\">"
                f"<span style=\"{LEDE_TAG_STYLE}\">要点透视</span><br />"
                f"<span style=\"{PARA_STYLE}\">{_render_text(value)}</span>"
                "</p>"
            )
            continue
        if label in META_LABELS:
            blocks.append(_render_meta(label, value))
            continue
        if stripped.startswith("- "):
            blocks.append(f"<p style=\"{BULLET_STYLE}\">• {_render_text(stripped[2:])}</p>")
            continue
        if stripped.startswith("*") and stripped.endswith("*"):
            blocks.append(f"<p style=\"{PARA_STYLE}color:#7d704d;\">{_render_text(stripped)}</p>")
            continue

        blocks.append(f"<p style=\"{PARA_STYLE}\">{_render_text(stripped)}</p>")

    close_section()
    blocks.append(f"<section style=\"{FOOTER_STYLE}\">万有预报，下期再见。</section>")
    blocks.append("</section>")
    return "\n".join(blocks)
