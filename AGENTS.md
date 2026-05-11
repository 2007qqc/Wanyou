# Wanyou Agents

This repository is organized as an agent pipeline. Each stage can be debugged alone, and the full run can produce Markdown, ranked raw, H5 HTML, browser-agent payload, and optional Xiumi draft output in one command.

## Pipeline Stages

### 1. Crawl

Collects source content from campus websites and WeChat public accounts:

- **Login-required** — 教务通知 (`crawlers_info`), 家园网 (`crawlers_myhome`). Share unified authentication via `wanyou/unified_auth.py`.
- **Public** — 图书馆 (`crawlers_lib`), 新清华学堂 (`crawlers_hall`), 物理系学术报告 (`crawlers_physics`).
- **WeChat** — Fetches articles via `down.mptext.top` API, classifies images with vision LLM (`wechat_pipeline`, `wechat_content`, `wechat_client`).

Code: `wanyou/crawlers_*.py`, `wanyou/wechat_pipeline.py`, `wanyou/unified_auth.py`, `wanyou/browser.py`

### 2. Raw & Ranked Raw

Writes raw Markdown, optionally runs LLM-based importance ranking:

- **Raw** — preserves full crawl output.
- **Ranked raw** — LLM scores items by relevance to physics undergraduates; useful for debugging selection quality.
- **Selected raw** (`--todo-richtext` mode) — picks top items per section for the final edition.

Code: `wanyou/raw_ranker.py`, `wanyou/decider.py`, `wanyou/temporal_filter.py`

### 3. Synthesize & Clean

Transforms ranked/selected raw into the final Wanyou Markdown:

- LLM text cleaning (`clean_markdown_document_with_llm`)
- Section transitions and formatting (`build_augmented_markdown`)
- Theme decoration (`decorate_markdown_with_theme`)

Code: `wanyou/utils_html.py`, `wanyou/synthesizer.py`, `wanyou/utils_llm.py`

### 4. Export

Produces final deliverables:

- **Markdown** — always generated.
- **H5 HTML** — themed standalone page.
- **DOCX** — via pypandoc (requires `pandoc` installed).
- **Browser Agent payload** — JSON for automated publishing.

Code: `generators/h5_generator.py`, `generators/browser_agent.py`, `generators/wechat_inline.py`

### 5. Xiumi Draft (optional)

Pushes final content into a Xiumi editor draft:

- Opens "My Xiumi" workspace, confirms login.
- Creates a new graphic draft, writes text, uploads images, applies layout, and saves.

Scripts: `scripts/run_wanyou_to_xiumi_draft.py`, `scripts/publish_xiumi_draft.py`

## Orchestration

- **Full pipeline** — `main.py::run_pipeline()` coordinates stages 1-4.
- **Entry scripts** — `skills/wanyou-full-run/scripts/run_wanyou_full_run.py` (full run CLI), `scripts/run_wanyou_to_xiumi_draft.py` (full run + Xiumi in one step).
- **Module runner** — `scripts/run_wanyou_module.py` lets you isolate a single source for debugging.

## Commands

Public-only smoke run:

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --public-only --skip-docx
```

Full run with login sources:

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --skip-docx
```

Skip WeChat while debugging campus crawlers:

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --skip-wechat --skip-docx
```

Ranked raw (inspect LLM selection quality):

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --ranked-raw
```

TODO richtext (build ranked raw, pick top items, then final Markdown + HTML):

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --todo-richtext --skip-docx
```

Full run + Xiumi draft (zero to saved draft):

```bash
python scripts/run_wanyou_to_xiumi_draft.py --with-login --skip-docx
```

Publish existing `.html` + `.md` to Xiumi:

```bash
python scripts/publish_xiumi_draft.py output/xxx/wanyou_xxx.html --markdown output/xxx/wanyou_xxx.md --title "万有预报"
```

Single module debug:

```bash
python scripts/run_wanyou_module.py wechat --md-only
python scripts/run_wanyou_module.py physics --raw-only --md-only
python scripts/run_wanyou_module.py login --raw-only --md-only
```

## Debug Order

1. Crawl first — inspect `*_raw.md` for source completeness.
2. Ranked raw next — inspect `*_ranked_raw.md` for LLM selection quality.
3. Synthesize — inspect `*.md` for text quality and section correctness.
4. Export — open `*.html` to verify richtext rendering.
5. Xiumi — use `--xiumi-dry-run` to test without saving; inspect `output/xiumi_debug/*.jsonl` for diagnostics.

## Known Issues

- Sandbox network can fail with `WinError 10013`.
- Selenium cache permissions can fail in restricted environments; `config.SELENIUM_CACHE_DIR` controls the cache path.
- Some campus URLs can go stale after site revisions; verify source URLs before changing parsers.
- Login-only sources should be skipped during public-only tests.
- WeChat API may return session errors (`ret=-1`, `ret=401`, `ret=200003`) — refresh `WECHAT_PUBLIC_API_KEY` and re-run.
- Xiumi page structure changes (CSS selectors, Angular scope) can break automation — check `output/xiumi_debug/*.jsonl` first.
