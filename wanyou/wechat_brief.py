"""公众号条目的两段式文案：要点透视 + 摘要。

要点透视只写形式信息（对象、时间、地点、报名/截止），摘要只写内容信息
（项目/活动简介、比赛或活动流程、亮点），两段都要短。本模块集中两段文案的
生成、解析、截断与规则兜底，以及 `--todo-richtext` 选稿后的补写逻辑，
让 wechat_pipeline 只负责抓取、筛选和输出。
"""

import json
import re

import config
from wanyou.markdown_document import parse_markdown_document
from wanyou.utils_dates import format_datetime_text
from wanyou.utils_html import _rule_clean_markdown
from wanyou.utils_llm import chat_complete


def _fallback_wechat_summary(item):
    for candidate in (item.get("digest") or "", item.get("content") or ""):
        cleaned = _rule_clean_markdown(candidate)
        if cleaned:
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            return cleaned[: getattr(config, "WECHAT_SUMMARY_MAX_CHARS", 110)]
    return ""


_META_SENTENCE_RE = re.compile(
    r"[^。；！？]*?(?:标注日期为|日期显示为|来源为|未提及|未交代|未见说明|材料未提供|原标题为)[^。；！？]*[。；！？]?"
)


def _strip_meta_sentences(text):
    """去掉“来源为…”“日期显示为…”“未提及…”这类编者视角的尾巴。

    模型即使被要求「材料没写的就省略」，仍爱补一句“日期显示为…/未提及报名方式”，
    在读者看来就是 AI 味，这里兜底删掉。
    """
    cleaned = _META_SENTENCE_RE.sub("", text or "").strip()
    return re.sub(r"\s+", " ", cleaned).strip()


def _title_only_summary(item):
    """没有正文材料时的兜底摘要。

    公众号「推广 | 项目信息 …」这类推送，微信读书只给标题、没有正文，但标题本身
    就是全部有效信息（哪个学校、哪一年、什么项目）。以前这种情况直接返回空摘要，
    结果这些条目被当成「没内容」丢掉——2027 寒假项目就是这么被漏掉的。
    """
    title = re.sub(r"^推广\s*[丨|｜]\s*", "", (item.get("title") or "").strip())
    title = re.sub(r"^项目信息\s*", "", title).strip()
    account = (item.get("account_keyword") or "").strip()
    if not title:
        return ""
    who = f"由{account}推广，" if account else ""
    where = f"公众号「{account}」原推送" if account else "原推送"
    return f"{title}。{who}课程安排、申请条件、费用与截止时间见{where}。"


_BRIEF_JSON_RE = re.compile(r"\{[\s\S]*\}")
_BRIEF_LEDE_LABEL_RE = re.compile(r"^(?:要点透视|点睛|lede)\s*[:：]", re.IGNORECASE)
_BRIEF_DIGEST_LABEL_RE = re.compile(r"^(?:摘要|digest|summary)\s*[:：]", re.IGNORECASE)
_BRIEF_LEDE_FIELD_RE = re.compile(
    r"(?:面向|对象|时间|日期|活动时间|报告时间|讲座时间|报名时间|报名截止|截止(?:时间|日期)?|地点)\s*[:：]\s*([^\n；;。]{1,40})"
)


def _norm_brief_text(text):
    return re.sub(r"[\s\u3000，。；：、！？“”\"'（）()—\-·｜|,.!:;]", "", text or "")


def _clip_brief_text(text, limit):
    """把一段话压到 limit 字以内，优先在分句/逗号处收住，不切半句；实在没有标点才硬截。"""
    cleaned = re.sub(r"\s+", " ", (text or "").replace("\n", "；")).strip(" ；;，,。")
    cleaned = re.sub(r"^[「『\"']|[」』\"']$", "", cleaned).strip()
    if not cleaned or len(cleaned) <= limit:
        return cleaned
    head = cleaned[:limit]
    cut = max(
        head.rfind("；"), head.rfind(";"),
        head.rfind("，"), head.rfind("、"),
        head.rfind("。"), head.rfind("！"), head.rfind("？"),
    )
    if cut >= max(limit // 3, 8):
        return head[:cut].rstrip(" ；;，,。、")
    return cleaned[:limit].rstrip(" ；;，,。、")


def _fallback_wechat_lede(snippet):
    """没有 LLM 时的要点透视兜底：只抽形式信息（时间/地点/对象/截止）。"""
    parts = []
    for match in _BRIEF_LEDE_FIELD_RE.finditer(snippet or ""):
        label = match.group(0).split("：")[0].split(":")[0].strip()
        value = re.sub(r"\s+", " ", match.group(1)).strip(" ，,；;")
        if not value:
            continue
        entry = f"{label}：{value}"
        if entry not in parts:
            parts.append(entry)
        if len(parts) >= 3:
            break
    return _clip_brief_text("；".join(parts), getattr(config, "WECHAT_LEDE_MAX_CHARS", 45))


def _parse_wechat_brief(result):
    """解析模型输出：优先 JSON，退而兼容「要点透视：… / 摘要：…」两行。"""
    if not result:
        return "", ""
    match = _BRIEF_JSON_RE.search(result)
    if match:
        try:
            payload = json.loads(match.group(0))
        except (ValueError, TypeError):
            payload = None
        if isinstance(payload, dict):
            lede = str(payload.get("lede") or payload.get("点睛") or "").strip()
            digest = str(
                payload.get("digest") or payload.get("summary") or payload.get("摘要") or ""
            ).strip()
            if lede or digest:
                return lede, digest

    lede = ""
    digest = ""
    for line in result.splitlines():
        line = line.strip()
        if not line:
            continue
        if _BRIEF_LEDE_LABEL_RE.match(line):
            lede = _BRIEF_LEDE_LABEL_RE.sub("", line).strip()
        elif _BRIEF_DIGEST_LABEL_RE.match(line):
            digest = _BRIEF_DIGEST_LABEL_RE.sub("", line).strip()
    return lede, digest


def summarize_wechat_item(item):
    """生成公众号条目的 (要点透视, 摘要)。

    要点透视只承担形式信息（对象、时间、地点、报名/截止），摘要只承担内容信息
    （项目/活动简介、比赛或活动流程、亮点）。两者都短，避免过去两条几乎同文。
    """
    title = (item.get("title") or "").strip()
    digest = _rule_clean_markdown(item.get("digest") or "")
    content = _rule_clean_markdown(item.get("content") or "")
    snippet = "\n".join(part for part in [digest, content] if part).strip()
    lede_limit = getattr(config, "WECHAT_LEDE_MAX_CHARS", 45)
    summary_limit = getattr(config, "WECHAT_SUMMARY_MAX_CHARS", 110)

    if not snippet:
        return "", _strip_meta_sentences(_title_only_summary(item))[:summary_limit]

    user_prompt = (
        f"标题: {title}\n"
        f"发布日期: {format_datetime_text(item)}\n"
        f"来源公众号: {(item.get('account_keyword') or '').strip()}\n"
        f"材料:\n{snippet[:2500]}"
    )
    result = chat_complete(
        config.WECHAT_BRIEF_SYSTEM_PROMPT,
        user_prompt,
        model=getattr(config, "WECHAT_SUMMARY_LLM_MODEL", "") or None,
        temperature=0,
        task_label=f"正在总结公众号内容：{title[:24]}",
    )

    lede, summary = _parse_wechat_brief(result)
    lede = _clip_brief_text(_strip_meta_sentences(lede), lede_limit)
    summary = _clip_brief_text(_strip_meta_sentences(summary), summary_limit)
    if not lede:
        lede = _fallback_wechat_lede(snippet)
    if not summary:
        summary = _clip_brief_text(
            _strip_meta_sentences(_fallback_wechat_summary(item)), summary_limit
        )
    # 摘要若只是把要点透视又说一遍，宁可不写，避免卡片上下两行同文。
    if summary and lede and _norm_brief_text(summary) == _norm_brief_text(lede):
        summary = ""
    return lede, summary


_BODY_CONTENT_SPLIT_RE = re.compile(r"\n内容[:：]\s*\n?")
_BODY_ACCOUNT_RE = re.compile(r"^来源公众号[:：]\s*(.+)$", re.MULTILINE)


def _split_wechat_body(body):
    """把公众号条目的元信息与「内容:」长正文拆开。"""
    match = _BODY_CONTENT_SPLIT_RE.search(body or "")
    if not match:
        return (body or "").strip(), ""
    head = body[: match.start()].rstrip()
    tail = body[match.end():].strip()
    return head, tail


def _add_wechat_brief_to_body(title, body, drop_full_content=True):
    """给选稿里的公众号条目补「要点透视/摘要」两段，并按需去掉冗余长正文。

    `--todo-richtext` / `--ranked-raw` 走 RAW_COLLECTION_MODE：公众号 raw 为了让排序
    看到全文，不生成摘要、还把正文整段写进 Markdown。选稿之后正文只剩冗余，这里按
    入选条目重新生成形式（要点透视）与内容（摘要）两段；摘要写不出来时保留正文兜底。
    """
    head, content_text = _split_wechat_body(body)
    if re.search(r"^要点透视[:：]", head or body or "", re.MULTILINE):
        # 已有两段（正常抓取模式会先写好要点透视/摘要）：只需按需去掉长正文，
        # 保留摘要和报名二维码图片。
        if content_text and drop_full_content:
            return head
        return body

    item = {"title": title}
    account = _BODY_ACCOUNT_RE.search(head)
    if account:
        item["account_keyword"] = account.group(1).strip()
    item["content"] = content_text or head

    lede, summary = summarize_wechat_item(item)
    lines = [head] if head else []
    if lede:
        lines.append(f"要点透视: {lede}")
    if summary:
        lines.append(f"摘要: {summary}")
    if content_text and (not summary or not drop_full_content):
        lines.append("内容:")
        lines.append(content_text)
    return "\n\n".join(lines).strip()


def enrich_wechat_briefs_in_markdown(markdown_text, *, drop_full_content=True):
    """对选稿 Markdown 里的公众号条目统一补「要点透视 + 摘要」，并去掉长正文。"""
    wechat_sections = list(config.WECHAT_SECTIONS)
    if not any(f"# {section}" in (markdown_text or "") for section in wechat_sections):
        return markdown_text

    rebuilt_sections = []
    for section in parse_markdown_document(markdown_text):
        section_title = section.get("title", "")
        parts = [f"# {section_title}", ""]
        is_wechat_section = section_title in wechat_sections
        for item in section.get("items", []):
            item_title = item.get("title", "")
            body = "\n".join(item.get("body_lines", [])).strip()
            if is_wechat_section and "来源公众号" in body:
                body = _add_wechat_brief_to_body(
                    item_title, body, drop_full_content=drop_full_content
                )
            parts.append(f"## {item_title}")
            parts.append("")
            if body:
                parts.append(body)
                parts.append("")
        rebuilt_sections.append("\n".join(parts).rstrip())
    return "\n\n".join(section for section in rebuilt_sections if section).strip() + "\n"
