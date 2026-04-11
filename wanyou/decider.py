from typing import Optional

import config
from wanyou.utils_llm import chat_complete


DECIDER_SYSTEM_PROMPT = (
    "你在为清华大学物理系本科生编辑每周《万有预报》。"
    "你的任务是判断一条信息是否应该保留。"
    "只保留在当前时间前一周内发布、且与物理系本科生直接相关的信息。"
    "如果发布者、面向群体、正文内容显示该信息主要面向研究生、教师、校外人员或与物理系本科生关系很弱，则不要保留。"
    "重点核对时间戳、发布者、面向群体，再结合正文判断。"
    "遇到校历时间第x周请这样判断：2026年4月11日是校历第7周周五，以此类推。"
    "只回答 YES 或 NO，不要输出其他内容。"
)


def _match_any(text: str, keywords) -> bool:
    return any(k for k in keywords if k and k in text)


def apply_keyword_rules(title: str, snippet: str = "") -> Optional[bool]:
    text = f"{title} {snippet}"
    if _match_any(text, config.LLM_FORCE_NO_KEYWORDS):
        return False
    if _match_any(text, config.LLM_FORCE_YES_KEYWORDS):
        return True
    return None


def build_context(site: str, title: str, date: str = "", snippet: str = "") -> str:
    parts = [
        f"站点: {site}",
        f"标题: {title}",
    ]
    if date:
        parts.append(f"发布时间: {date}")
    if snippet:
        parts.append(f"正文与摘要: {snippet}")
    parts.extend(
        [
            "筛选规则:",
            "1. 只接受生成万有预报前一周内发布的信息。",
            "2. 只接受与清华大学物理系本科生直接相关的信息。",
            "3. 重点看时间戳、发布者、面向群体，再参考正文内容。",
            "4. 像研究生会、研究生招生、教师招聘等与物理系本科生关系不强的信息，应判为 NO。",
        ]
    )
    return "\n".join(parts)


def should_copy_with_llm(site: str, title: str, date: str = "", snippet: str = "") -> Optional[bool]:
    if not config.LLM_ENABLED:
        return None
    rule = apply_keyword_rules(title, snippet)
    if rule is not None:
        return rule
    context = build_context(site, title, date, snippet)
    result = chat_complete(
        DECIDER_SYSTEM_PROMPT,
        context,
        max_tokens=5,
        temperature=0,
        task_label="正在判断条目是否保留",
    )
    if not result:
        return None
    head = result.strip().upper()
    if head.startswith("YES"):
        return True
    if head.startswith("NO"):
        return False
    return None


def resolve_copy_decision(site: str, title: str, date: str = "", snippet: str = "") -> bool:
    decision = should_copy_with_llm(site, title, date, snippet)
    if decision is not None:
        return bool(decision)
    if getattr(config, "INTERACTIVE_REVIEW", False):
        return input(f'是否拷贝“{title}”的信息?(y/n, default y)\n') != "n"
    return bool(getattr(config, "DEFAULT_COPY_WHEN_UNDECIDED", True))
