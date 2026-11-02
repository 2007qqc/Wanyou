"""日期/时间高亮：H5 和秀米内联两条导出链路共用同一套匹配规则。

之前只有 H5 那条链路标红（`h5_generator._highlight_time_text`），秀米走的是
Markdown → 内联 HTML 这条路，完全没有高亮，所以同一期内容在网页里是红的、
在公众号草稿里不是。规则也各写一份，容易走样，这里统一收口。

匹配顺序即优先级，必须先长后短：像「10月8日—23日」「9月25—27日」这种区间，
尾巴上没有「月」字，只有先整段吃掉，才不会被拆成「10月8日」+ 漏标的「23日」。
"""

import re

TIME_PATTERNS = (
    # 2026年10月8日 / 2026-10-08 / 2026/10/8，允许原文里的「10 月 17 日」这类空格
    r"20\d{2}\s*[年\-/.]\s*\d{1,2}\s*[月\-/.]\s*\d{1,2}\s*[日号]?(?:\s*[（(][^）)]{0,12}[）)])?",
    # 10月8日—23日 / 9月25—27日 / 10月1日至7日 / 11月2—20日
    r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]?\s*[—–\-~～至到]\s*(?:\d{1,2}\s*月\s*)?\d{1,2}\s*[日号]?",
    # 10月8日 / 10月8号
    r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]?(?:\s*[（(][^）)]{0,12}[）)])?",
    # 7:30—22:30 / 19:00-21:00
    r"\d{1,2}\s*[:：]\s*\d{2}\s*[—–\-~～至到]\s*\d{1,2}\s*[:：]\s*\d{2}",
    # 14:30 / 8:00
    r"\d{1,2}\s*[:：]\s*\d{2}",
    # 第6周 / 第 16 周
    r"第\s*\d{1,2}\s*周",
    # 周六 / 星期三
    r"(?:周|星期)[一二三四五六日天]",
    # 今天 / 本周 / 近期 …
    r"(?:今天|明天|后天|今日|本周|下周|近期|即日起)",
)

TIME_RE = re.compile("|".join(TIME_PATTERNS))

# H5 用 class（样式写在 <style> 里），秀米只能吃行内样式，所以包法做成参数。
H5_TIME_SPAN = "<span class='time-highlight'>"
INLINE_TIME_SPAN = '<span style="color:#f96e57;font-weight:700;">'


def highlight_time_spans(text: str, opening: str = H5_TIME_SPAN, closing: str = "</span>") -> str:
    """把 text 里的日期/时间包成高亮 span。text 必须是**已转义**的 HTML 片段。"""
    if not text:
        return text or ""
    return TIME_RE.sub(lambda match: f"{opening}{match.group(0)}{closing}", text)
