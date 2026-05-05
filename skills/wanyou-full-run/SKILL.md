---
name: wanyou-full-run
description: Run the Wanyou pipeline end to end and produce raw Markdown, ranked raw, final Markdown, H5 HTML, browser-agent payload output, and optional Xiumi draft output. Use when Codex needs one command to generate or debug the full Wanyou workflow, especially for public-only smoke runs or full runs with login sources.
---

# Wanyou Full Run

## Workflow

1. Use module runs first when debugging one source.
2. Choose `--public-only` for smoke tests and external debugging.
3. Choose `--with-login` when campus credentials are available.
4. The current full workflow is: source pages and APIs -> raw Markdown -> LLM-ranked raw -> selected and cleaned final Markdown/HTML -> optional Xiumi draft.
5. Inspect the raw Markdown path first when a source is missing.
6. Inspect ranked raw before changing prompts or selection logic.
7. Open the HTML output to verify richtext before sending content to Xiumi.

## Commands

Public-only full run:

```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --public-only --skip-docx
```

Full run with unified-auth sources:

```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --todo-richtext --skip-docx
```

Full run from zero to Xiumi draft:

```powershell
python scripts/run_wanyou_to_xiumi_draft.py --with-login --skip-docx
```

Skip WeChat while debugging campus crawlers:

```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --skip-wechat --skip-docx
```

## Debug Rules

- Prefer `scripts/run_wanyou_module.py <module>` before blaming the full pipeline.
- Ranked raw should rank and select items without doing an extra LLM text-cleaning pass.
- Use H5 output as the default richtext debug target.
- If WeChat fails with session errors, refresh `WECHAT_PUBLIC_API_KEY` before re-running.
- Keep the final artifact paths from the script output for later inspection.
