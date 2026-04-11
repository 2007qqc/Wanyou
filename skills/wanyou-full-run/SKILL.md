---
name: wanyou-full-run
description: Run the Wanyou pipeline end to end and produce raw Markdown, final Markdown, H5 HTML, and browser-agent payload output. Use when Codex needs one command to generate or debug the full Wanyou workflow, especially for public-only smoke runs or full runs with login sources.
---

# Wanyou Full Run

## Workflow

1. Use module runs first when debugging one source.
2. Choose `--public-only` for smoke tests and external debugging.
3. Choose `--with-login` when campus credentials are available.
4. Inspect the raw Markdown path first.
5. Inspect the final Markdown after summaries and transitions.
6. Open the HTML output to verify richtext before looking at DOCX.

## Commands

Public-only full run:

```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --public-only --skip-docx
```

Full run with unified-auth sources:

```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login
```

Skip WeChat while debugging campus crawlers:

```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --skip-wechat --skip-docx
```

## Debug Rules

- Prefer `scripts/run_wanyou_module.py <module>` before blaming the full pipeline.
- Use H5 output as the default richtext debug target.
- If WeChat fails with session errors, refresh `WECHAT_PUBLIC_API_KEY` before re-running.
- Keep the final artifact paths from the script output for later inspection.
