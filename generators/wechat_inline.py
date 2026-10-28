import html
import os
import re
from typing import List, Tuple

from generators.h5_generator import FOOTER_LINE, HEADER_SUBTITLE_LINE, HEADER_TITLE_LINE, SECTION_LEADS
from wanyou.image_paths import clean_markdown_image_target, is_remote_or_data_image, resolve_existing_image_path
from wanyou.markdown_tables import table_to_blocks

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
TIME_VALUE_STYLE = "color:#f96e57;font-weight:700;"
LINK_STYLE = "color:#8b5600;text-decoration:none;border-bottom:1px solid rgba(139,86,0,0.24);word-break:break-all;"
BULLET_STYLE = f"margin:8px 0;padding-left:1.1em;color:{INK};font-size:15px;line-height:1.9;"
IMAGE_STYLE = "display:block;width:100%;max-width:100%;height:auto;margin:12px auto;"
FOOTER_STYLE = "margin:28px 0 0;padding:16px 14px 0;text-align:center;"
FOOTER_NOTE_STYLE = (
    f"margin:12px 0 0;border-top:4px solid {ACCENT};background:rgba(245,200,51,0.10);padding:12px 14px;"
    f"border-radius:0 0 16px 16px;font-size:14px;color:{MUTED};line-height:1.8;"
)
# 手机上（375–414px）正文可用宽度约 330px。原来用 overflow-x:auto 撑横向滚动，
# 但公众号和秀米都会把 overflow 剥掉，结果是宽表整列被裁、日期列被拆成
# 「10 / 月 / 29 / 日」。改成：窄表固定列宽 + 只留横线；宽表一行一卡。
TABLE_WRAP_STYLE = f"margin:12px 0;padding:10px;border:1px solid {ACCENT_LINE};border-radius:8px;background:#ffffff;"
TABLE_STYLE = "width:100%;max-width:100%;border-collapse:collapse;table-layout:fixed;font-size:13px;line-height:1.65;"
TH_STYLE = "padding:8px 7px;border-bottom:1px solid rgba(213,165,28,0.45);background:rgba(245,200,51,0.22);color:#8f6a00;font-weight:700;text-align:left;vertical-align:top;word-break:break-word;overflow-wrap:anywhere;"
TD_STYLE = "padding:8px 7px;border-bottom:1px solid rgba(213,165,28,0.22);color:#3e3e3e;text-align:left;vertical-align:top;word-break:break-word;overflow-wrap:anywhere;"
TD_ALT_STYLE = "padding:8px 7px;border-bottom:1px solid rgba(213,165,28,0.22);background:rgba(245,200,51,0.07);color:#3e3e3e;text-align:left;vertical-align:top;word-break:break-word;overflow-wrap:anywhere;"
TABLE_CARD_STYLE = f"margin:8px 0 0;padding:10px 12px;border-left:3px solid {ACCENT};background:rgba(245,200,51,0.10);border-radius:0 8px 8px 0;"
TABLE_CARD_TITLE_STYLE = f"margin:0 0 6px;color:{ACCENT_INK};font-size:14px;font-weight:700;line-height:1.55;word-break:break-word;overflow-wrap:anywhere;"
TABLE_CARD_ROW_STYLE = "margin:0;padding:2px 0;color:#3e3e3e;font-size:13.5px;line-height:1.7;word-break:break-word;overflow-wrap:anywhere;"
TABLE_CARD_LABEL_STYLE = f"display:inline-block;min-width:4.8em;margin-right:6px;color:{MUTED};font-weight:700;"


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


_EMPTY_META_RE = re.compile(r"^([^:：]{1,12})[:：]\s*$")


def _empty_meta_label(text: str) -> str:
    """「日期:」「票价:」这种标签独占一行、值写在接下来的行里。"""
    match = _EMPTY_META_RE.match((text or "").strip())
    if not match:
        return ""
    label = match.group(1).strip()
    return label if label in META_LABELS else ""


def _collect_meta_values(lines: List[str], start: int, limit: int = 4) -> Tuple[List[str], int]:
    """从 `start` 起收集标签的取值：连续的 `- ` 列表项，或者紧跟的一行正文。"""
    values: List[str] = []
    index = start
    while index < len(lines) and len(values) < limit:
        candidate = lines[index].strip()
        if not candidate:
            if values:
                break
            index += 1
            continue
        if candidate.startswith("- "):
            values.append(candidate[2:].strip())
            index += 1
            continue
        if not values:
            values.append(candidate)
            index += 1
        break
    return values, index


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


_ESCAPE_RE = re.compile(r"\\([\\`*{}\[\]()#+\-.!_>|~])")


def _render_text(value: str) -> str:
    # 「1\. 测试项目」这类被 Markdown 转义过的标点，渲染时还原成普通字符
    return html.escape(_ESCAPE_RE.sub(r"\1", _strip_emphasis(value or "")))


def _render_meta(label: str, value: str) -> str:
    escaped_label = html.escape(label)
    if label == "链接" and re.match(r"^https?://", value or ""):
        # 这里绝不能用 <a href>：公众号编辑器会把 mp.weixin.qq.com 的链接当成
        # 「图文消息」去校验归属，不是本号的推送就报「请勿插入不合法的图文消息
        # 链接」；外链也会被剥掉。正文里不做超链接，纯文本反而更稳。
        rendered_value = f"<span style=\"{LINK_STYLE}\">{html.escape(value)}</span>"
    else:
        value_style = TIME_VALUE_STYLE if label in TIME_LABELS else "color:#4f432f;"
        rendered_value = f"<span style=\"{value_style}\">{_render_text(value)}</span>"
    return f"<p style=\"{META_ROW_STYLE}\"><span style=\"{META_LABEL_STYLE}\">{escaped_label}</span>{rendered_value}</p>"


def _is_table_row(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _is_table_separator(text: str) -> bool:
    return bool(re.match(r"^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$", text.strip()))


_URL_ONLY_RE = re.compile(r"^https?://\S+$")


def _cell_html(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    if _URL_ONLY_RE.match(value):
        # 同 _render_meta：表格里的 URL 也只留文字，不用 <a href>
        return f"<span style=\"{LINK_STYLE}\">{html.escape(value)}</span>"
    return html.escape(value)


def _render_table_layout(plan: dict) -> str:
    """按 `table_to_blocks` 的决策渲染：窄表→固定列宽表格，宽表→一行一卡。"""
    mode = plan.get("mode")
    if mode == "table":
        colgroup = "".join(f"<col style=\"width:{width}%\" />" for width in plan["widths"])
        head = ""
        if plan.get("show_header", True):
            head = "<thead><tr>" + "".join(
                f"<th style=\"{TH_STYLE}\">{_cell_html(cell)}</th>" for cell in plan["header"]
            ) + "</tr></thead>"
        body_rows = []
        for row_index, row in enumerate(plan["rows"]):
            cell_style = TD_ALT_STYLE if row_index % 2 else TD_STYLE
            body_rows.append(
                "<tr>" + "".join(f"<td style=\"{cell_style}\">{_cell_html(cell)}</td>" for cell in row) + "</tr>"
            )
        return (
            f"<section style=\"{TABLE_WRAP_STYLE}\">"
            f"<table style=\"{TABLE_STYLE}\"><colgroup>{colgroup}</colgroup>"
            f"{head}<tbody>{''.join(body_rows)}</tbody></table></section>"
        )
    if mode == "cards":
        parts = ["<section style=\"margin:10px 0 0;\">"]
        for card in plan["cards"]:
            parts.append(f"<section style=\"{TABLE_CARD_STYLE}\">")
            if card["title"]:
                parts.append(f"<p style=\"{TABLE_CARD_TITLE_STYLE}\">{_cell_html(card['title'])}</p>")
            for field in card["fields"]:
                parts.append(
                    f"<p style=\"{TABLE_CARD_ROW_STYLE}\">"
                    f"<span style=\"{TABLE_CARD_LABEL_STYLE}\">{html.escape(field['label'])}</span>"
                    f"{_cell_html(field['value'])}</p>"
                )
            parts.append("</section>")
        parts.append("</section>")
        return "".join(parts)
    return ""


def _render_markdown_table(table_lines: List[str]) -> str:
    return _render_table_layout(table_to_blocks(table_lines))


def markdown_to_wechat_inline_html(markdown_text: str, markdown_path: str = "") -> str:
    blocks: List[str] = [f"<section style=\"{PAGE_STYLE}\">"]
    section_open = False
    card_open = False
    card_title = ""
    pending: List[str] = []

    def flush_paragraph():
        """把连续正文行攒成一段。

        Markdown 里相邻的普通行属于同一段（软换行）。原来一行一个 <p>，
        爬回来的摘要一旦被硬折行，就变成一屏碎行、行距忽大忽小。
        这里用 <br /> 保留原本的断行，但段间距只算一次。
        """
        nonlocal pending
        if not pending:
            return
        blocks.append("<p style=\"" + PARA_STYLE + "\">" + "<br />".join(_render_text(line) for line in pending) + "</p>")
        pending = []

    def close_card():
        nonlocal card_open, card_title
        flush_paragraph()
        if card_open:
            blocks.append("</section>")
            card_open = False
        card_title = ""

    def close_section():
        nonlocal section_open
        close_card()
        if section_open:
            blocks.append("</section>")
            section_open = False

    def open_section(title: str):
        nonlocal section_open
        close_section()
        lead = SECTION_LEADS.get(title, "把这部分内容整理成适合快速阅读的信息卡片。")
        blocks.append(f"<section style=\"{SECTION_STYLE}\">")
        blocks.append(f"<span style=\"{SECTION_TAG_STYLE}\">本期栏目</span>")
        blocks.append(f"<span style=\"{SECTION_TAG_ARROW_STYLE}\"></span>")
        blocks.append(f"<h2 style=\"{SECTION_TITLE_STYLE}\">{html.escape(title)}</h2>")
        blocks.append(f"<p style=\"{SECTION_LEAD_STYLE}\">{html.escape(lead)}</p>")
        section_open = True

    def open_card(title: str):
        nonlocal card_open, card_title
        close_card()
        blocks.append(f"<section style=\"{CARD_STYLE}\">")
        blocks.append(f"<span style=\"{CARD_NOTCH_STYLE}\"></span>")
        blocks.append(f"<h3 style=\"{CARD_TITLE_STYLE}\">{html.escape(title)}</h3>")
        card_open = True
        card_title = title

    blocks.append(f"<section style=\"{HERO_BAR_STYLE}\"></section>")
    blocks.append(f"<section style=\"{HERO_STYLE}\">")
    blocks.append(f"<span style=\"{HERO_MARK_STYLE}\">清物语 · 物理系风格</span>")
    blocks.append(f"<h1 style=\"{H1_STYLE}\">{PAGE_TITLE}</h1>")
    blocks.append(f"<p style=\"{SUBTITLE_STYLE}\">清华大学物理系校园信息整理</p>")
    blocks.append("</section>")

    lines = (markdown_text or "").splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if _is_table_row(stripped) and index + 1 < len(lines) and _is_table_separator(lines[index + 1].strip()):
            flush_paragraph()
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
                flush_paragraph()
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
            flush_paragraph()
            continue
        if stripped in {HEADER_TITLE_LINE, HEADER_SUBTITLE_LINE, FOOTER_LINE}:
            flush_paragraph()
            continue

        image_match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if image_match:
            flush_paragraph()
            alt = image_match.group(1).strip()
            if alt in THEME_BADGE_ALTS:
                continue
            src = html.escape(_resolve_image_src(image_match.group(2), markdown_path), quote=True)
            blocks.append(f"<img src=\"{src}\" alt=\"{html.escape(alt or '配图')}\" style=\"{IMAGE_STYLE}\" />")
            continue

        if stripped.startswith("# "):
            # 正文自带的 H1 如果就是刊名，hero 已经写过一次，别再开一个同名栏目
            if stripped[2:].strip() in {"万有预报", PAGE_TITLE}:
                flush_paragraph()
                continue
            open_section(stripped[2:].strip())
            continue
        if stripped.startswith("## "):
            if not section_open:
                open_section("未分类")
            open_card(stripped[3:].strip())
            continue
        if stripped.startswith("### "):
            flush_paragraph()
            blocks.append(f"<p style=\"{SUBHEAD_STYLE}\">{html.escape(stripped[4:].strip())}</p>")
            continue

        label, value = _split_label_value(stripped)
        if label == "要点透视":
            flush_paragraph()
            blocks.append(
                f"<section style=\"{LEDE_STYLE}\">"
                f"<span style=\"{LEDE_TAG_STYLE}\">要点透视</span>"
                f"<p style=\"{LEDE_TEXT_STYLE}\">{_render_text(value)}</p>"
                "</section>"
            )
            continue
        if label in META_LABELS:
            flush_paragraph()
            blocks.append(_render_meta(label, value))
            continue
        # 「日期:」独占一行、值在下面 —— 不接住就会变成「正文 + 两条列表」
        empty_label = _empty_meta_label(stripped)
        if empty_label:
            values, next_index = _collect_meta_values(lines, index)
            if values:
                flush_paragraph()
                blocks.append(_render_meta(empty_label, " / ".join(values)))
                index = next_index
                continue
        if stripped.startswith("- "):
            flush_paragraph()
            blocks.append(f"<p style=\"{BULLET_STYLE}\">• {_render_text(stripped[2:])}</p>")
            continue
        if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 2:
            flush_paragraph()
            blocks.append(f"<p style=\"{PARA_STYLE}color:#7d704d;\">{_render_text(stripped)}</p>")
            continue

        # 正文又把卡片标题重复了一遍，删掉；标题常带「推广 | 」这类前缀，
        # 所以除了全等，正文是标题的长后缀也算重复
        if card_title and (
            stripped == card_title or (len(stripped) >= 12 and card_title.endswith(stripped))
        ):
            flush_paragraph()
            continue

        pending.append(stripped)

    close_section()
    blocks.append(
        f"<section style=\"{FOOTER_STYLE}\">"
        f"<p style=\"{FOOTER_NOTE_STYLE}\">本期万有预报到这里就结束了。<br />万有预报，下期再见。</p>"
        "</section>"
    )
    blocks.append("</section>")
    return "\n".join(blocks)
