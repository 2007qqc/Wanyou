---
name: wanyou-richtext-export
description: Export final Wanyou Markdown into H5 HTML and browser-agent payload without re-running crawlers or LLM filtering. Use when Codex needs to validate layout, theme, richtext output, or agent payload generation.
---

# Wanyou Richtext Export

## Purpose

Use this skill after final Markdown already exists. It exports H5 HTML and optional browser-agent payload from the Markdown file.

## Commands

Export HTML and agent payload:

```powershell
python skills/wanyou-richtext-export/scripts/run_wanyou_richtext_export.py output/module_wechat_YYYYMMDD_HHMM/wanyou_wechat.md
```

Choose output paths:

```powershell
python skills/wanyou-richtext-export/scripts/run_wanyou_richtext_export.py output/final.md --html output/final.html --agent-payload output/final_agent.json
```

Only export HTML:

```powershell
python skills/wanyou-richtext-export/scripts/run_wanyou_richtext_export.py output/final.md --skip-agent-payload
```

Only export browser-agent payload:

```powershell
python skills/wanyou-richtext-export/scripts/run_wanyou_richtext_export.py output/final.md --skip-html
```

## Debug Rules

- Treat HTML as the primary richtext verification target.
- If DOCX is needed, use the full pipeline and verify local `pandoc` first.
- Richtext export should not change crawler or LLM filtering behavior.
