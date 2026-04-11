---
name: wanyou-llm-filter
description: Apply Wanyou LLM keep/drop decisions, item compression, summaries, section transitions, and theme Markdown decoration to raw Markdown. Use when Codex needs to retest filtering prompts or summary quality without re-running crawlers.
---

# Wanyou LLM Filter

## Purpose

Use this skill after crawler modules have produced a raw Markdown file. It reads raw Markdown, applies LLM filtering and summaries, limits item length, and writes final Markdown.

The current filtering policy is:

- Keep only information published within one week before the Wanyou run.
- Keep only information directly relevant to Tsinghua Physics undergraduates.
- Pay special attention to timestamp, publisher, target audience, and body text.
- For overloaded sections, keep at most 4 items.
- WeChat is handled by the crawler module as latest 5 articles by publish time.

## Commands

```powershell
python skills/wanyou-llm-filter/scripts/run_wanyou_llm_filter.py output/module_wechat_YYYYMMDD_HHMM/wanyou_wechat_raw.md
```

Choose a specific output path:

```powershell
python skills/wanyou-llm-filter/scripts/run_wanyou_llm_filter.py input_raw.md --output output/final.md
```

Skip theme decoration:

```powershell
python skills/wanyou-llm-filter/scripts/run_wanyou_llm_filter.py input_raw.md --no-theme
```

## Debug Rules

- If an item is kept unexpectedly, inspect `wanyou/decider.py` and `wanyou/synthesizer.py` prompts first.
- If no LLM call happens, check `LLM_ENABLED`, provider settings, and API key environment variables.
- If output is too long, inspect the item compression path in `wanyou/synthesizer.py`.
