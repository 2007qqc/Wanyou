from typing import Optional

import config
from wanyou.prompt_preferences import KEEP_DROP_PREFERENCE_RULES
from wanyou.utils_llm import chat_complete
from wanyou.filter_debug import log_filter_decision


DECIDER_SYSTEM_PROMPT = (
    '你在为清华大学物理系本科生编辑每周《万有预报》。'
    + '请从物理系本科生的角度判断一条信息是否应该保留。'
    + KEEP_DROP_PREFERENCE_RULES
    + '优先判断截止时间、活动时间、报告时间是否仍然有效；只有找不到这些有效期信息时，才参考发布时间。'
    + '重点核对截止时间、活动时间、发布时间、发布者、面向群体，再结合正文判断；不能仅因发布时间较早就排除仍未截止或尚未发生的信息。'
    + '遇到校历时间第x周请这样判断：2026年4月11日是校历第7周周五，以此类推。'
    + '只回答 YES 或 NO，不要输出其他内容。'
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
        parts.append(f"已知日期: {date}")
    if snippet:
        parts.append(f"正文与摘要: {snippet}")
    parts.extend(
        [
            "筛选规则:",
            "1. 优先接受截止时间未过、活动尚未发生或仍在报名期的信息；发布时间只作为兜底依据。",
            "2. 只接受与清华大学物理系本科生直接相关的信息。",
            "3. 重点看截止时间、活动时间、发布时间、发布者、面向群体，再参考正文内容。",
            "4. 优先保留课业、教务、物理学术报告、科研训练、暑校、SRT、星火、挑战杯等有行动价值的信息。",
            "5. 研究生、博士生、教师、内部管理事项，以及一般通识讲座、泛宣传、弱相关活动，应谨慎判低或判 NO。",
        ]
    )
    return "\n".join(parts)


def should_copy_with_llm(site: str, title: str, date: str = "", snippet: str = "") -> Optional[bool]:
    if not config.LLM_ENABLED:
        log_filter_decision(section=site, title=title, status="undecided", reason="llm_disabled", stage="decider", date=date)
        return None
    rule = apply_keyword_rules(title, snippet)
    if rule is not None:
        log_filter_decision(
            section=site,
            title=title,
            status="kept" if rule else "dropped",
            reason="keyword_rule",
            stage="decider",
            date=date,
        )
        return rule
    context = build_context(site, title, date, snippet)
    result = chat_complete(
        DECIDER_SYSTEM_PROMPT,
        context,
        model=getattr(config, "DECIDER_LLM_MODEL", "") or None,
        max_tokens=64,
        temperature=0,
        task_label="正在判断条目是否保留",
    )
    if not result:
        log_filter_decision(section=site, title=title, status="undecided", reason="llm_empty", stage="decider", date=date)
        return None
    head = result.strip().upper()
    if head.startswith("YES"):
        log_filter_decision(section=site, title=title, status="kept", reason="llm_yes", stage="decider", date=date)
        return True
    if head.startswith("NO"):
        log_filter_decision(section=site, title=title, status="dropped", reason="llm_no", stage="decider", date=date)
        return False
    log_filter_decision(
        section=site,
        title=title,
        status="undecided",
        reason="llm_unparseable",
        stage="decider",
        date=date,
        details={"raw_result": result[:200]},
    )
    return None


def resolve_copy_decision(site: str, title: str, date: str = "", snippet: str = "") -> bool:
    decision = should_copy_with_llm(site, title, date, snippet)
    if decision is not None:
        return bool(decision)
    if getattr(config, "INTERACTIVE_REVIEW", False):
        return input(f'是否拷贝“{title}”的信息?(y/n, default y)\n') != "n"
    return bool(getattr(config, "DEFAULT_COPY_WHEN_UNDECIDED", True))
