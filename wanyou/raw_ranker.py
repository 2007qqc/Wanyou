import json
import os
import re
from functools import lru_cache
from typing import Dict, List

import config
from wanyou.filter_debug import log_filter_decision
from wanyou.prompt_preferences import (
    KEEP_DROP_PREFERENCE_RULES,
    RAW_RANKING_SCORE_GUIDE,
    RAW_RANKING_TRAINING_EXAMPLES,
)
from wanyou.synthesizer import parse_markdown_document
from wanyou.utils_html import _rule_clean_markdown, clean_crawled_markdown
from wanyou.utils_issue_filter import current_issue_cutoff, parse_datetime_text
from wanyou.utils_llm import chat_complete
from wanyou.run_clock import effective_run_date


def _strip_images(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text or "")
    text = re.sub(r"\[图片文字\s*\d+\].*", "", text)
    return text


def _clean_text(text: str, title: str = "", *, clean_with_llm: bool = False) -> str:
    text = _strip_images(text)
    if clean_with_llm:
        cleaned = clean_crawled_markdown(text, source=title or "raw", use_llm=True) or text
    else:
        cleaned = _rule_clean_markdown(text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned or "")
    return cleaned.strip()


def _extract_publish_date(item: dict) -> str:
    content = item.get("content", "") or ""
    for pattern in (
        r"(?:发布时间|发布日期|日期)[:：]\s*([^\n]+)",
        r"(20\d{2}[年\-/.]\d{1,2}[月\-/.]\d{1,2}(?:日)?)",
        r"(\d{1,2}月\d{1,2}日)",
    ):
        match = re.search(pattern, content)
        if match:
            return match.group(1).strip()
    return ""


def _is_recent_publish(item: dict) -> tuple[bool, str, str]:
    raw_date = _extract_publish_date(item)
    parsed = parse_datetime_text(raw_date)
    cutoff = current_issue_cutoff()
    if parsed is None:
        return True, "no_parseable_publish_date_keep", raw_date
    if parsed >= cutoff:
        return True, "publish_recent", parsed.isoformat(timespec="minutes")
    if _has_current_or_future_date(item.get("content", "") or ""):
        return True, "publish_old_but_effective", parsed.isoformat(timespec="minutes")
    return False, "publish_older_than_cutoff", parsed.isoformat(timespec="minutes")


def _normalize_heading(text: str) -> str:
    return re.sub(r"\s+", "", text or "").strip()


@lru_cache(maxsize=32)
def _load_tendency_reference(section_name: str) -> str:
    """Load bounded section-specific preference samples from tendency.md."""
    aliases = {_normalize_heading(section_name)}
    if section_name == "图书馆信息":
        aliases.add("图书馆")

    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tendency.md"))
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return ""

    headings = list(re.finditer(r"^(#{1,3})\s+(.+?)\s*$", text, re.M))
    for pos, heading in enumerate(headings):
        title = _normalize_heading(heading.group(2))
        if title not in aliases:
            continue
        level = len(heading.group(1))
        start = heading.end()
        end = len(text)
        for next_heading in headings[pos + 1 :]:
            if len(next_heading.group(1)) <= level:
                end = next_heading.start()
                break
        section_text = text[start:end].strip()
        if "重要性评分" not in section_text and "物理系本科生偏好评分" not in section_text:
            return ""
        section_text = re.sub(r"\n{3,}", "\n\n", section_text)
        examples = _summarize_tendency_examples(section_text)
        if examples:
            return examples[:3200]
        return section_text[:3000]
    return ""


def _summarize_tendency_examples(section_text: str) -> str:
    examples = []
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", section_text, re.M))
    for pos, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[pos + 1].start() if pos + 1 < len(matches) else len(section_text)
        body = section_text[start:end]
        score_match = re.search(
            r"物理系本科生偏好评分[：:]\s*(\d{1,3})(?:\s*/\s*100)?(?:[（(]([^）)]*)[）)])?",
            body,
        )
        if not score_match:
            score_match = re.search(r"重要性评分[：:]\s*(\d{1,3})(?:\s*/\s*100)?", body)
        if not score_match:
            continue
        score = max(0, min(100, int(score_match.group(1))))
        reason = (score_match.group(2) or "").strip() if len(score_match.groups()) >= 2 else ""
        reason_line = re.search(r"(?:原因|理由|排序依据)[：:]\s*([^\n]+)", body)
        if reason_line:
            reason = reason_line.group(1).strip()
        examples.append(f"- {title} => {score}/100；{reason}" if reason else f"- {title} => {score}/100")
    if not examples:
        return ""
    return "当前版块人工评分样例：\n" + "\n".join(examples)


def _all_detected_dates_before_run(text: str) -> bool:
    dates = []
    for pattern in (
        r"20\d{2}[年\-/.]\d{1,2}[月\-/.]\d{1,2}(?:日)?(?:\s*\d{1,2}[:：]\d{2})?",
        r"\d{1,2}月\d{1,2}日(?:\s*\d{1,2}[:：]\d{2})?",
    ):
        for match in re.finditer(pattern, text or ""):
            parsed = parse_datetime_text(match.group(0))
            if parsed is not None:
                dates.append(parsed.date())
    if not dates:
        return False
    today = effective_run_date()
    return all(day < today for day in dates)


def _has_current_or_future_date(text: str) -> bool:
    for pattern in (
        r"20\d{2}[年\-/.]\d{1,2}[月\-/.]\d{1,2}(?:日)?(?:\s*\d{1,2}[:：]\d{2})?",
        r"\d{1,2}月\d{1,2}日(?:\s*\d{1,2}[:：]\d{2})?",
    ):
        for match in re.finditer(pattern, text or ""):
            parsed = parse_datetime_text(match.group(0))
            if parsed is not None and parsed.date() >= effective_run_date():
                return True
    return False


def _lib_expired_low_score_cap(title: str, text: str) -> int:
    title_text = title or ""
    if re.search(r"LaTeX|Word|论文写作", title_text, re.I):
        return 20
    if re.search(r"EndNote|NoteExpress|投稿指南|学术规范|知网AI|数据库课堂", title_text, re.I):
        return 15
    if re.search(r"知识产权|专利|金融|经济|WRDS|Capital IQ|医药|许可|商业|会计", f"{title_text}\n{text}", re.I):
        return 10
    return 12


def _fallback_score(item: dict) -> dict:
    title = item.get("title", "")
    content = item.get("content", "")
    text = f"{title}\n{content}"
    score = 35

    if re.search(r"选课|退课|排课|调课|调休|考试|成绩|培养方案|学籍|毕业|课程", text, re.I):
        score += 45
    if re.search(r"物理系学术报告|学术报告|seminar|colloquium|讲座", text, re.I):
        score += 35
    if re.search(r"SRT|星火|学推|挑战杯|暑校|科研训练|奖学金|奖助|保研", text, re.I):
        score += 30
    if re.search(r"宿舍|熄灯|交通|通行|校庆安排|校园网|志愿工时|第二成绩单|献血", text, re.I):
        score += 22
    if re.search(r"AI|人工智能|量子|能源|交叉", text, re.I):
        score += 12
    if re.search(r"报名|申请|截止|决赛|展示|公示|结果|答辩|观摩", text, re.I):
        score += 10

    if re.search(r"研究生|博士生|博士后|教师|教职工|辅导员|管理人员|教学建设|课程建设", text, re.I):
        score -= 55
    if re.search(r"文化素质教育讲座|生态文明十五讲|新人文讲座|王国维学术讲座|学术之道|世界文学|礼仪|思政|宣传片|口号", text, re.I):
        score -= 35
    if re.search(r"社团骨干|内部培训|工作总结|口号发布|组织生活", text, re.I):
        score -= 20
    if re.search(r"儿童剧|影像展|音乐会|演讲大赛|文化节|工作坊|嘉年华|揭幕活动|升国旗仪式", text, re.I):
        score -= 18

    return {"score": max(0, min(100, score)), "reason": "fallback_keyword_score"}


def _apply_score_guardrails(section_name: str, item: dict, score: int, reason: str = "") -> dict:
    title = str(item.get("title", "") or "")
    content = str(item.get("content", "") or "")
    text = f"{title}\n{content}"
    head_text = f"{title}\n{content[:600]}"
    lowered_reason = (reason or "").strip()
    adjusted = int(score)
    tags: List[str] = []
    is_publicity_like = bool(re.search(r"口号|揭幕|亮点预告|抢先看|开幕式|倒计时|预热", text, re.I))
    is_showcase_like = bool(re.search(r"风采展|优秀个人|人物专访|人物故事|成长故事|校友故事", title, re.I))

    if re.search(r"文化素质教育讲座|生态文明十五讲|新人文讲座|王国维学术讲座|学术之道|世界文学", text, re.I):
        adjusted = min(adjusted, 20)
        tags.append("cap_general_culture_lecture")
    if re.search(r"英语风采演讲|英语竞赛|演讲大赛|辩论赛|礼仪课堂|工作坊|嘉年华|文创|游园|诗乐会|音乐会|文化节", text, re.I):
        adjusted = min(adjusted, 35)
        tags.append("cap_general_activity")
    if is_publicity_like:
        adjusted = min(adjusted, 25)
        tags.append("cap_publicity")
    if (
        re.search(r"研究生|博士生|博士后|教师|教职工|课程建设|学位授权点建设", text, re.I)
        and not re.search(r"本科生|本科|全体学生|广大师生", text, re.I)
    ):
        adjusted = min(adjusted, 10)
        tags.append("cap_non_undergrad")

    if section_name == "物理系学术报告" or re.search(r"物理系学术报告|学术报告|colloquium|seminar", title, re.I):
        adjusted = max(adjusted, 80)
        tags.append("floor_physics_report")
    if (
        not is_publicity_like
        and not is_showcase_like
        and re.search(r"暑期学校|暑校|SRT|星火|学推|挑战杯|科研训练|保研", text, re.I)
        and re.search(
        r"报名|申请|截止|公示|结果|决赛|获奖|答辩|观摩",
        head_text,
        re.I,
        )
    ):
        adjusted = max(adjusted, 55)
        tags.append("floor_actionable_training")
    if re.search(r"宿舍|熄灯|交通|通行|第二成绩单|志愿工时|献血", head_text, re.I):
        adjusted = max(adjusted, 45)
        tags.append("floor_life_impact")

    if section_name == "图书馆信息":
        if re.search(r"开馆|闭馆|考试周|阅览室|座位|预约|借还|数据库访问|校外访问|资源访问|服务调整|系统维护", text, re.I):
            adjusted = max(adjusted, 90)
            tags.append("floor_lib_service_impact")
        if re.search(r"知识产权|专利|金融|经济|WRDS|Capital IQ|医药|许可|商业|会计", text, re.I):
            adjusted = min(adjusted, 15)
            tags.append("cap_lib_weak_topic")
        if re.search(r"EndNote|NoteExpress|投稿指南|学术规范|知网AI|数据库课堂", title, re.I):
            adjusted = min(adjusted, 20)
            tags.append("cap_lib_research_tool")
        if re.search(r"LaTeX|Word|论文写作", title, re.I):
            adjusted = min(adjusted, 30)
            tags.append("cap_lib_research_tool")
        if _all_detected_dates_before_run(text):
            adjusted = min(adjusted, _lib_expired_low_score_cap(title, text))
            tags.append("cap_expired_activity")

    final_reason = lowered_reason
    if tags:
        suffix = "；score_guardrail=" + ",".join(tags)
        final_reason = (f"{lowered_reason}{suffix}" if lowered_reason else suffix.lstrip("；"))[:180]
    return {"score": max(0, min(100, adjusted)), "reason": final_reason}


def _score_section_items(section_name: str, items: List[dict]) -> Dict[str, dict]:
    if not items:
        return {}
    fallback = {}
    for i, item in enumerate(items, start=1):
        fallback_meta = _fallback_score(item)
        fallback[str(i)] = _apply_score_guardrails(
            section_name,
            item,
            int(fallback_meta.get("score", 0)),
            str(fallback_meta.get("reason") or "fallback_keyword_score"),
        )
    if not getattr(config, "LLM_ENABLED", False):
        return fallback

    candidates = []
    for index, item in enumerate(items, start=1):
        content = (item.get("content", "") or "")[:900]
        candidates.append(
            f"{index}. 标题: {item.get('title', '')}\n正文摘录:\n{content}"
        )
    system_prompt = (
        "你在为清华大学物理系本科生整理《万有预报》 raw 全量信息。"
        + f"当前运行日期是 {effective_run_date().isoformat()}。"
        + "请先据此判断活动、报名、影响时间是否已经过去；过期条目要明显降权，但仍应保留低分区间内的相对排序，不要把所有低分项目都压成同一个分数。"
        + "人工评分样例中的非零分代表该信息的基准偏好；如果候选条目已经过期，应在这个基准上降权，同时保持专利/金融/医药、文献工具、LaTeX/Word 等类别之间的相对差异。仍在当前或未来生效的长期通知可以保留高分。"
        + "不要删除任何条目，只需为每条信息按对物理系本科生的重要性打 0-100 分。"
        + KEEP_DROP_PREFERENCE_RULES
        + RAW_RANKING_SCORE_GUIDE
        + RAW_RANKING_TRAINING_EXAMPLES
        + "优先看截止时间、活动时间、发布者、面向群体和正文内容。"
        + "你的分数应尽量贴近真实物理系本科生的信息获取偏好，而不是平均意义上的校园资讯热度。"
        + "如果同一条内容在 tendency.md 一类训练样本中会被认为偏低分，就不要因为文案热闹或发布者知名而抬高分数。"
        + "如果当前版块给出了人工评分样例，必须优先对齐样例中的“物理系本科生偏好评分”，不要沿用泛校园资讯的重要性评分。"
        + "图书馆信息尤其要区分：开馆、考试周、自习座位、资源访问和服务调整等基础设施通知可高分；一般专利、金融、医药、数据库、文献工具或论文工具讲座通常低分。过期活动应降到低分区，但仍要参照 tendency.md 示例给低分项目排序。"
        + "先在心里判断它属于哪一档：高优先、中优先、低优先、极低优先，再从对应分段内给分，避免分数漂移。"
        + "请在 reason 中明确说明给分的核心依据，例如：课业影响、科研训练价值、物理相关性、是否处于报名/决赛/结果阶段、是否只对研究生有效、是否只是一般宣传。"
        + 'JSON 输出格式：{"items":[{"index":1,"score":80,"band":"high","reason":"..."}]}。'
    )
    tendency_reference = _load_tendency_reference(section_name)
    if tendency_reference:
        system_prompt += (
            "下面是 tendency.md 中与当前版块对应的人工偏好样例，请优先对齐这些样例的相对排序和分数尺度："
            + tendency_reference
        )
    user_prompt = f"版块: {section_name}\n\n" + "\n\n".join(candidates)
    result = chat_complete(
        system_prompt,
        user_prompt,
        model=getattr(config, "RAW_RANKING_LLM_MODEL", "") or None,
        max_tokens=max(5000, min(8000, 900 * len(items))),
        temperature=0,
        task_label=f"正在为 raw 条目打分排序：{section_name}",
    )
    if not result:
        return fallback
    match = re.search(r"\{[\s\S]*\}", result)
    if not match:
        return fallback
    try:
        payload = json.loads(match.group(0))
    except Exception:
        return fallback
    scores = dict(fallback)
    for entry in payload.get("items") or []:
        try:
            index = str(int(entry.get("index")))
            score = int(float(entry.get("score")))
        except Exception:
            continue
        item = items[int(index) - 1] if 0 < int(index) <= len(items) else {}
        scores[index] = _apply_score_guardrails(
            section_name,
            item,
            max(0, min(100, score)),
            str(entry.get("reason") or "llm_score")[:120],
        )
    return scores


def build_ranked_raw_markdown(markdown_text: str, current_markdown_path: str = "", *, clean_with_llm: bool = False) -> str:
    _ = current_markdown_path
    rendered_sections = []
    for section in parse_markdown_document(markdown_text):
        section_name = section.get("title", "")
        items = []
        for item in section.get("items", []):
            title = item.get("title", "")
            raw_content = "\n".join(item.get("body_lines", [])).strip()
            candidate = {"title": title, "content": raw_content}
            keep, reason, basis = _is_recent_publish(candidate)
            log_filter_decision(
                section=section_name,
                title=title,
                status="kept" if keep else "dropped",
                reason=reason,
                stage="ranked_raw_publish_filter",
                date=basis,
            )
            if keep:
                content = _clean_text(raw_content, title=title, clean_with_llm=clean_with_llm)
                items.append({"title": title, "content": content})
        scores = _score_section_items(section_name, items)
        indexed_items = []
        for index, item in enumerate(items, start=1):
            meta = scores.get(str(index), _fallback_score(item))
            indexed_items.append((int(meta.get("score", 0)), index, item, meta))
        indexed_items.sort(key=lambda row: (-row[0], row[1]))

        parts = [f"# {section_name}", ""]
        if not indexed_items:
            parts.extend(["## 占位卡片", "", "本版块 raw 模式未抓取到一周内发布的条目。", ""])
        for score, _index, item, meta in indexed_items:
            parts.append(f"## {item['title']}")
            parts.append("")
            parts.append(f"重要性评分: {score}/100")
            reason = str(meta.get("reason") or "").strip()
            if reason:
                parts.append("")
                parts.append(f"排序依据: {reason}")
            if item.get("content"):
                parts.append("")
                parts.append(item["content"])
            parts.append("")
        rendered_sections.append("\n".join(parts).strip())
    return "\n\n".join(section for section in rendered_sections if section).strip() + "\n"


def _extract_score_and_content(item: dict) -> tuple[int, str]:
    score = 0
    content_lines = []
    for line in item.get("body_lines", []) or []:
        stripped = line.strip()
        match = re.match(r"重要性评分:\s*(\d{1,3})/100", stripped)
        if match:
            score = max(0, min(100, int(match.group(1))))
            continue
        if stripped.startswith("排序依据:"):
            continue
        content_lines.append(line)

    content = "\n".join(content_lines).strip()
    content = re.sub(r"\n{3,}", "\n\n", content)
    return score, content.strip()


def build_selected_raw_markdown_from_ranked(
    ranked_markdown_text: str,
    *,
    default_limit: int = 4,
    wechat_limit: int = 5,
) -> str:
    rendered_sections = []
    for section in parse_markdown_document(ranked_markdown_text):
        section_name = section.get("title", "")
        limit = wechat_limit if section_name == "其他公众号信息" else default_limit
        ranked_items = []

        for index, item in enumerate(section.get("items", []), start=1):
            title = str(item.get("title", "") or "").strip()
            if not title or title == "占位卡片":
                continue
            score, content = _extract_score_and_content(item)
            ranked_items.append((score, index, title, content))

        ranked_items.sort(key=lambda row: (-row[0], row[1]))

        parts = [f"# {section_name}", ""]
        for score, _index, title, content in ranked_items[:limit]:
            _ = score
            parts.append(f"## {title}")
            parts.append("")
            if content:
                parts.append(content)
                parts.append("")
        rendered_sections.append("\n".join(parts).rstrip())

    return "\n\n".join(section for section in rendered_sections if section).strip() + "\n"
