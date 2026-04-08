---
name: wanyou-full-run
description: Run the Wanyou pipeline end to end and produce raw Markdown, final Markdown, H5 HTML, and browser-agent payload output. Use when Codex needs one command to generate or debug the full Wanyou workflow, especially for public-only smoke runs or full runs with login sources.
---

# Wanyou Full Run

## Workflow

1. Choose `--public-only` for smoke tests and external debugging.
2. Choose `--with-login` when campus credentials are available.
3. Inspect the raw Markdown path first.
4. Inspect the final Markdown after summaries and transitions.
5. Open the HTML output to verify richtext before looking at DOCX.

## Commands

```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --public-only --skip-docx
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login
```

## Debug Rules

- Prefer public-only runs before blaming login-only sources.
- Use H5 output as the default richtext debug target.
- Keep the final artifact paths from the script output for later inspection.
