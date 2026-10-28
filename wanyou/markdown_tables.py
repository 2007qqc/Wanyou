"""把 Markdown 表格拆成「手机端友好」的结构。

公众号正文的可视宽度只有 375–414px，减去卡片内边距后约 330px。把 4–5 列的
Markdown 表格原样塞进去，观感是灾难：日期列会被拆成「10 / 月 / 29 / 日」，
不带换行机会的长 URL 那一列会撑到 600px 以上，整列被裁掉（微信不认
`overflow-x`，没有横向滚动）。

所以这里只做**布局决策**，不负责样式：渲染留给各自的 generator。

- 窄表（≤3 列）→ ``table``：保留表格形态，按内容宽度分配列宽。
- 宽表（≥4 列）→ ``cards``：一行卡片，首列当小标题，其余列按「标签：值」
  逐行排。这是公众号里通行的做法，一行信息一屏内能读全。
"""

import re
import unicodedata
from typing import List, Sequence, Tuple

MAX_TABLE_COLUMNS = 3
"""超过这个列数就改成一行一卡，再宽的表在手机上没法读。"""

_SEPARATOR_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")


def is_table_row(text: str) -> bool:
    stripped = (text or "").strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def is_table_separator(text: str) -> bool:
    return bool(_SEPARATOR_RE.match((text or "").strip()))


def split_table_row(text: str) -> List[str]:
    stripped = text.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.replace(r"\|", "|").strip() for cell in re.split(r"(?<!\\)\|", stripped)]


def _visual_width(text: str) -> int:
    """CJK 全角算 2、半角算 1，用来估列宽。"""

    total = 0
    for ch in text or "":
        total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total


def parse_markdown_table(table_lines: Sequence[str]) -> Tuple[List[str], List[List[str]]]:
    """返回 (表头, 数据行)；表头为空时用第一行数据顶替。"""

    rows = [
        split_table_row(line)
        for line in table_lines
        if is_table_row(line) and not is_table_separator(line)
    ]
    if not rows:
        return [], []

    max_cols = max(len(row) for row in rows)
    for row in rows:
        row.extend([""] * (max_cols - len(row)))

    # 整列都空的列直接丢掉（Markdown 里常有多打的 |
    keep = [i for i in range(max_cols) if any(row[i] for row in rows)]
    if not keep:
        return [], []
    rows = [[row[i] for i in keep] for row in rows]

    header = rows[0]
    body = rows[1:]
    # 表头全空说明这其实是无表头的表：第一行也是数据
    if not any(cell.strip() for cell in header):
        header = [""] * len(rows[0])
        body = rows
    return header, body


def _column_widths(header: List[str], body: List[List[str]]) -> List[int]:
    """按内容视觉宽度分配百分比列宽，夹在 14%–46% 之间。"""

    cols = len(header)
    if cols == 1:
        return [100]

    weights = []
    for index in range(cols):
        samples = [header[index]] + [row[index] for row in body[:12]]
        widths = [_visual_width(cell) for cell in samples if cell]
        # 取中位数附近，避免一格超长把整列撑爆
        widths.sort()
        typical = widths[len(widths) // 2] if widths else 6
        weights.append(max(6, min(typical, 28)))

    total = sum(weights) or cols
    raw = [weight / total * 100 for weight in weights]

    low, high = 14.0, 46.0
    clamped = [min(high, max(low, value)) for value in raw]
    scale = 100.0 / sum(clamped)
    percentages = [round(value * scale) for value in clamped]

    # 四舍五入后补/减到正好 100
    diff = 100 - sum(percentages)
    percentages[percentages.index(max(percentages))] += diff
    return percentages


def table_to_blocks(table_lines: Sequence[str]) -> dict:
    """把表格行变成渲染指令。

    返回 ``{"mode": "table"|"cards"|"empty", ...}``：

    - ``table``: ``{"mode","header","rows","widths"}``
    - ``cards``: ``{"mode","cards":[{"title","fields":[{"label","value"}]}]}``
    """

    header, body = parse_markdown_table(table_lines)
    if not header:
        return {"mode": "empty"}

    if len(header) <= MAX_TABLE_COLUMNS:
        return {
            "mode": "table",
            "header": header,
            "rows": body,
            "widths": _column_widths(header, body),
            # 表头整行都空（比如上面那条分隔线其实是第一行数据）就别画空表头
            "show_header": any(cell.strip() for cell in header),
        }

    labels = [(cell.strip() or f"第{index + 1}列") for index, cell in enumerate(header)]
    cards = []
    for row in body:
        title = row[0].strip()
        fields = []
        for index in range(1, len(row)):
            value = row[index].strip()
            if not value:
                continue
            fields.append({"label": labels[index], "value": value})
        cards.append({"title": title, "fields": fields})
    return {"mode": "cards", "cards": cards}
