---
name: wanyou-richtext-export
description: Export Wanyou Markdown into H5 HTML, browser-agent payload, and optional DOCX backup. Use when Codex needs to validate or debug final richtext output without re-running every crawler.
---

# Wanyou Richtext Export

## Workflow

1. Start from final Markdown.
2. Export H5 HTML with `generators/h5_generator.py`.
3. Export browser-agent payload with `generators/browser_agent.py`.
4. Export DOCX only when local `pandoc` is available.

## Debug Rules

- Treat HTML as the primary richtext verification target.
- If DOCX fails, verify `pandoc` before changing Markdown or template logic.
- Use [references/outputs.md](references/outputs.md) for output expectations.
