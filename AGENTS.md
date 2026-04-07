# Wanyou Agents

This repository is organized as an agent pipeline. Each stage can be debugged alone, and the full run can produce Markdown, H5 HTML, and browser-agent payload output in one command.

## Modules

`Campus Crawl`
- Code: `wanyou/crawlers_*.py`
- Skill: `skills/wanyou-campus-crawl`
- Responsibility: fetch campus-site content, separate login-only and public sources, and write raw Markdown blocks.

`LLM Filter`
- Code: `wanyou/decider.py`, `wanyou/synthesizer.py`, `wanyou/utils_llm.py`
- Skill: `skills/wanyou-llm-filter`
- Responsibility: keep/drop decisions, summaries, transitions, and provider routing.

`Richtext Export`
- Code: `generators/h5_generator.py`, `generators/browser_agent.py`
- Skill: `skills/wanyou-richtext-export`
- Responsibility: turn Markdown into H5 HTML and browser-agent payload, and optionally DOCX.

`Full Run`
- Code: `main.py`
- Skill: `skills/wanyou-full-run`
- Responsibility: orchestrate the whole pipeline once and return final paths.

## One-Run Commands

Public-only smoke run:

```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --public-only --skip-docx
```

Full run with login sources:

```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login
```

## Debug Order

1. Run the campus crawl stage first.
2. Inspect raw Markdown before touching summaries.
3. Run LLM filter and summaries after confirming the raw crawl.
4. Export rich text last.

## Known Timeout Causes

- Sandbox network can fail with `WinError 10013`.
- Selenium cache permissions can fail in restricted environments; the project now uses `config.SELENIUM_CACHE_DIR`.
- Some campus URLs can go stale after site revisions; verify source URLs before changing parsers.
- Login-only sources should be skipped during public-only tests.
