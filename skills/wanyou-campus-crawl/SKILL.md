---
name: wanyou-campus-crawl
description: Collect content for Wanyou from campus sites, split login-only and public sources, and diagnose crawl failures. Use when Codex needs to fetch or debug library, hall, physics, info, or myhome source data before any LLM or richtext step.
---

# Wanyou Campus Crawl

## Workflow

1. Decide whether the run is `public-only` or `with-login`.
2. Test `lib` and `hall` first because they are the most stable public sources.
3. Add `physics` after confirming the source URL is still valid.
4. Add `info` and `myhome` only when credentials are available.
5. Inspect the raw Markdown before debugging later stages.

## Debug Rules

- Treat `WinError 10013` as an environment restriction first, not a parser bug.
- Treat empty selector results as a possible URL or page-revision issue.
- Use `config.SELENIUM_CACHE_DIR` when Selenium cache permissions are involved.
- Use [references/sites.md](references/sites.md) for source-specific notes.
