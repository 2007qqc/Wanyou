# Wanyou Agents

This repository is organized as an agent pipeline. Each stage can be debugged alone, and the full run can produce Markdown, ranked raw, H5 HTML, browser-agent payload, and optional Xiumi draft output in one command.

## Pipeline Stages

### 1. Crawl

Collects source content from campus websites and WeChat public accounts:

- **Login-required** — 教务通知 (`crawlers_info`), 家园网 (`crawlers_myhome`). Share unified authentication via `wanyou/unified_auth.py`.
- **Public** — 图书馆 (`crawlers_lib`), 新清华学堂 (`crawlers_hall`), 物理系学术报告 (`crawlers_physics`). 物理系学术报告卡片只写“报告时间/地点/人/摘要”，不写页面发布日期。
- **WeChat** — Lists articles via weread.qq.com (drives a dedicated debug Chrome), then fetches each article's **full body and images** through `/web/mp/content?reviewId=...` (the list API only gives a short excerpt), and detects registration QR codes with OpenCV (`wechat_pipeline`, `wechat_brief`, `wechat_qr`, `wechat_content`, `wechat_client`, `weread_client`). Targets 4 accounts — 清华大学学生会, 清华青年科创, 清华大学学生社团, 清华大学学生公益 — configured in `config.WEREAD_ACCOUNT_BOOK_IDS`; section routing is account-first (`WECHAT_ACCOUNT_SECTION_RULES`).

Code: `wanyou/crawlers_*.py`, `wanyou/wechat_pipeline.py`, `wanyou/wechat_brief.py`, `wanyou/wechat_qr.py`, `wanyou/unified_auth.py`, `wanyou/browser.py`

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

Code: `wanyou/utils_html.py`, `wanyou/synthesizer.py`, `wanyou/utils_llm.py`; Markdown `# 栏目` / `## 条目` parsing is shared via `wanyou/markdown_document.py` (used by synthesizer, raw ranker, WeChat brief enrichment and final cleaning).

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

**Login rules (learned the hard way):**

- Xiumi auth lives in a **session-scoped cookie**. Closing or force-killing the browser
  loses it, so login and save must happen in the same window. Persisting a profile is
  not enough on its own.
- The script never clicks a login entry (`config.XIUMI_LOGIN_AUTO_CLICK = False`); that
  link leads to WeChat's OAuth page, which looks like an account-authorization prompt.
- "Page shows 退出登录, editor still says 正在登录/登录后可保存颜色信息" means the session is
  gone. `_xiumi_authed` checks the editor text plus visible login links for this reason;
  trusting the cached header avatar produces false positives and an endless
  fill → save → "保存前需要重新登录" loop.
- Xiumi raises a native `confirm("你有未保存的修改…")` on navigation. A CDP
  `Page.addScriptToEvaluateOnNewDocument` neutralizes it; otherwise every Selenium call
  after the first navigation dies with `UnexpectedAlertPresentException`.
- `--edit-draft-id <id>` updates an existing draft in place instead of creating another one.

### 6. WeChat freshness gate

Weread's list API only returns an excerpt, so the gate now uses the **full article body**
from `/web/mp/content?reviewId=...` (see `weread_client.fetch_article_contents`): dates are
parsed from title + 要点透视 + 摘要 + the first 4000 chars of the body, and the LLM judge is
given the real publish timestamp (`format_datetime_text`) instead of an empty field. This is
what rescues "报名/招募" posts whose event dates only appear in the body — e.g. 烛光计划
(活动时间 11.13–14) used to be dropped as `unknown`. The gate still applies: retrospective
wording → drop, a year later than the publish date → keep, every parsed date before the
publish date → drop, otherwise ask the LLM and **drop on `unknown`**. Posts with a title but
no body are never dropped for being thin — `_title_only_summary` writes a fallback digest.

**原文链接也来自这个接口**：`/web/mp/content` 返回的完整页面里带 `msg_link`
（`?__biz=…&mid=…&idx=…&sn=…`），`CONTENT_JS` 会把它一起抽出来写进 `item["url"]`，
成稿卡片就是真链接，不再是「原文链接待补」。`originalId` 依旧拼不出链接（`/s/<id>`
返回 200 但是「参数错误」页），别再走那条路。`WECHAT_LINKS_TSV` 只作为覆盖/兜底。

Date parsing lives in `wanyou/date_ranges.py` (`parse_dates`, `parse_deadline_dates`) and
handles what the old single regex missed: `11.5` / `11/7` (numeric, context-gated so `v1.5`
and `12.5%` are not dates), ranges `11月7—8日` / `11.7-11.8` / `11月30日—12月2日`, and
year rollover (`1月10日` in a December issue → next year). Deadline detection also scans
「截止/报名截止」 lines with that parser, so `deadline_on_publish_day` fires for `11.2` too.
Regression it fixed: 2026-11-02 的《无偿献血》写 11.7–11.8，曾被判 `llm:expired:…早于见刊日`。

**Image-only posts** (body shorter than `WECHAT_IMAGE_ONLY_MAX_CHARS` = 120 but carrying
images) have no parseable date; instead of asking the LLM and dropping on `unknown`, they are
kept with reason `image_only_keep` when `WECHAT_IMAGE_ONLY_KEEP` is on (default). Retro
titles still get dropped by the rule above, so only forward-looking posters survive.

Two extra publication-window rules:

- **Deadline on the publish date (next Monday) is not kept** — `temporal_filter` uses
  `deadline_on_publish_day` and `wechat_freshness` has the same check; the issue ships that
  morning, so a deadline that same day is not worth listing.
- **Notices published before the current window are not selected** — `published_in_current_window`
  (`utils_issue_filter`) drops 教务/家园网/图书馆开馆类公告 whose detail date is older than
  `WANYOU_RUN_DATE`; the crawler logs `published_before_window`. Event-style sources
  (hall/physics/library events) are not date-limited this way because they are announced ahead.

### 7. WeChat copy split + registration QR

WeChat cards deliberately carry two different short fields:

- **要点透视** (`item["lede"]`, ≤ `WECHAT_LEDE_MAX_CHARS` = 45): form only — audience, date/time, place, sign-up/deadline.
- **摘要** (`item["summary"]`, ≤ `WECHAT_SUMMARY_MAX_CHARS` = 110): content only — what the project/event is, its format or flow, highlights.

`wechat_brief.summarize_wechat_item` produces both in one JSON LLM call (`{"lede":..., "digest":...}`) with rule-based fallbacks, writes them to raw Markdown as `要点透视:` / `摘要:` lines, and `synthesizer._enrich_items` promotes the pinned lede into the card box. `wechat_freshness.decide_item` reads the lede too, because dates now live there. `--todo-richtext` runs WeChat in `RAW_COLLECTION_MODE` (long body, no summaries), so after item selection `main.run_pipeline` calls `wechat_brief.enrich_wechat_briefs_in_markdown` to add the two fields and drop the redundant long body. The final LLM cleaning pass skips WeChat sections (`config.WECHAT_SECTIONS`) so the split is not rewritten. Since one push is often forwarded by several accounts, `_dedupe_cross_account_titles` collapses identical normalized titles within 3 days, keeping the copy with more material.

Registration QR codes are handled by `wechat_qr`: body images whose preceding text mentions 二维码/扫码/问卷/报名/群 are downloaded; OpenCV decodes them or, for logo-obstructed codes, accepts a detection with a black/white-ratio guard to avoid photo false positives. Up to `WECHAT_QR_MAX_IMAGES` images are saved under `WECHAT_QR_IMAGE_DIR` and written after the 摘要 as `![报名二维码](...)`; the placement is before the `内容:` block so the long body can be trimmed without losing the code. WeChat cards do **not** print the push publish date/time (`write_md_stream` omits `日期:`/`发布时间:`), and `raw_ranker` skips its publish-date re-filter for WeChat sections because the collection stage already applied the 7-day window.

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
- WeChat listing (`WECHAT_SOURCE="weread"`) needs a logged-in debug Chrome. `-2041` is the Tencent captcha: `call_with_risk_control_wait` focuses that window, prints a prompt for the user, retries every 5s, reports progress every 60s and resumes automatically once the captcha clears (cap `WEREAD_RISK_WAIT_SECONDS`, default 600s). Do **not** kill the job, restart that Chrome, or re-run while it waits — the login and captcha trust live in that window. `-2010` means the weread login expired, and `-2003` means the request parameters were malformed (`errMsg` says so verbatim — check the `bookId` and the URL actually sent; it is **not** rate limiting).
- 「近一周」的窗口口径在 `wanyou/recent_window.py`：默认按校历周对齐（上一校历周周一 00:00 起），不是滚动 `now - 7×24h`；抓取、正文补全、prefilter 三处共用同一 cutoff。`WECHAT_RECENT_ALIGN=week|day|rolling` 可切换。
- Rollback route `WECHAT_SOURCE="mptext"` may return session errors (`ret=-1`, `ret=401`, `ret=200003`) — refresh `WECHAT_PUBLIC_API_KEY` and re-run.
- Xiumi page structure changes (CSS selectors, Angular scope) can break automation — check `output/xiumi_debug/*.jsonl` first.
