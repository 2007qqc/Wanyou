from typing import Optional

import config
from wanyou.utils_llm import llm_decide_yes_no


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
    parts = [f"站点: {site}", f"标题: {title}"]
    if date:
        parts.append(f"日期: {date}")
    if snippet:
        parts.append(f"摘要: {snippet}")
    return "\n".join(parts)


def should_copy_with_llm(site: str, title: str, date: str = "", snippet: str = "") -> Optional[bool]:
    if not config.LLM_ENABLED:
        return None
    rule = apply_keyword_rules(title, snippet)
    if rule is not None:
        return rule
    context = build_context(site, title, date, snippet)
    return llm_decide_yes_no(context)
