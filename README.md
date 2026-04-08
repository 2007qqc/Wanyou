# Wanyou

Wanyou generates a weekly Tsinghua Physics campus briefing from multiple sources.

It currently supports:
- campus site crawlers
- shared Tsinghua SSO login for protected sources
- WeChat public account collection
- LLM-assisted cleaning, summarization, and temporal filtering
- Markdown / HTML / Browser Agent payload export

## Requirements

- Python 3.10+
- Microsoft Edge
- Edge WebDriver
- `pandoc` if you need DOCX export

Install dependencies:
```powershell
python -m pip install -r requirements.txt
python -m pip install PyYAML
```

## Quick Start

Public sources only:
```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --public-only --skip-docx
```

Full run with login sources:
```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login
```

## Login and Secondary Verification

The program now uses one shared Edge session for Tsinghua SSO.
It logs in once, then reuses that session for both `Teaching Notices` and `MyHome Notices`.

Behavior:
- the terminal asks for SSO username and password once
- password input is masked
- if Edge already has a valid login session, the program reuses it

If SSO enters secondary verification:
1. the program keeps a visible Edge window open
2. the user finishes verification manually in Edge
3. the user returns to the terminal and presses Enter
4. crawling continues

## Date Filtering Strategy

This is the main behavior to know before using the tool.

### Default cutoff

By default, the cutoff is `7 days before the moment the program starts`.

Example:
- if you run the program at `2026-04-08 15:30`
- the default cutoff is `2026-04-01 15:30`
- items older than that are skipped as early as possible

### User-defined cutoff

You can override the default in [config.py](./config.py):

```python
NOTICE_PREFILTER_CUTOFF = "2026-04-01 00:00"
```

Rule priority:
- if `NOTICE_PREFILTER_CUTOFF` is empty, use `now - 7 days`
- if `NOTICE_PREFILTER_CUTOFF` is set, use the configured value

Accepted common formats:
- `2026-04-01 00:00`
- `2026-04-01`
- `2026?4?1? 00:00`

### Early filtering behavior

The program tries to filter before fetching detail pages:
- if a list page already shows a usable timestamp, it filters there first
- if the title already appeared in the previous issue, it skips it there too
- only items without usable list-level time info continue to the detail page

This reduces:
- unnecessary detail-page requests
- unnecessary HTML cleaning
- unnecessary LLM calls

### Previous issue deduplication

The program automatically reads the previous generated `wanyou_YYYYMMDD_HHMM.md` and skips same-title items in the same section.

## Current Source Behavior

- `Teaching Notices`
  - adapted to the new teaching notice page
  - if the page opens successfully but there are no valid new notices in the current time window, it reports that as `no valid notices this issue`, not as a generic crawler failure
- `MyHome Notices`
  - reuses the shared SSO browser session
  - filters by date as early as possible
- `Library`
  - filters by list-level notice date or event date before deeper processing when possible
- `New Tsinghua Auditorium`
  - skips outdated events and previously used titles before downloading posters
- `Physics Reports`
  - filters by list-level time and previous-issue titles first
  - if there is no new report in the current window, it should be treated as `no new reports`, not as a crawler crash
- `WeChat sources`
  - filters by API timestamp and previous-issue title before content fetch
  - only retained articles continue to full-content fetch and summary generation

## LLM Usage

Default model settings are in [config.py](./config.py):

```python
LLM_ENABLED = True
LLM_PROVIDER = "deepseek"
LLM_MODEL = "deepseek-chat"
```

Common environment variables:
```powershell
$env:DEEPSEEK_API_KEY = "your-key"
$env:OPENAI_API_KEY = "your-key"
$env:GEMINI_API_KEY = "your-key"
$env:ZHIPUAI_API_KEY = "your-key"
$env:OCR_SPACE_API_KEY = "your-key"
$env:WECHAT_PUBLIC_API_KEY = "your-key"
```

Runtime prompts for LLM steps are explicit, for example:
- `Waiting for LLM: checking item freshness`
- `Waiting for LLM: compressing a single item summary`
- `Waiting for LLM: summarizing WeChat content`
- `Waiting for LLM: extracting physics report fields`

## WeChat Public Accounts

WeChat collection uses the `down.mptext.top` API instead of direct WeChat login.

Set:
```powershell
$env:WECHAT_PUBLIC_API_KEY = "your-key"
```

Run separately:
```powershell
python wechat_public.py
```

Current behavior:
- prefilter by timestamp and previous issue title
- fetch content only for retained items
- export summaries instead of full articles by default

## Debug Files

Each run writes outputs to:
```text
output/<timestamp>/
```

Important debug directory:
```text
output/<timestamp>/debug/
```

Common files:
- `shared_login_attempt.txt`
- `shared_after_login.html`
- `shared_after_manual_auth.html`
- `info_after_login.html`
- `info_after_open_teaching.html`
- `info_llm_hint.json`
- `myhome_after_login.html`

Suggested debugging order:
1. check authentication and page snapshots in `debug/`
2. check `*_raw.md`
3. check final `*.md` and `*.html`

## Outputs

Typical outputs:
- `wanyou_<timestamp>_raw.md`
- `wanyou_<timestamp>.md`
- `wanyou_<timestamp>.html`
- `wanyou_<timestamp>_agent.json`
- `wanyou_<timestamp>.docx` if `pandoc` is installed

## Recommended User Strategy

For normal weekly use:
1. keep `NOTICE_PREFILTER_CUTOFF = ""`
2. let the program use the default `now - 7 days` window
3. only set a manual cutoff when backfilling an old issue or rerunning a special issue window
4. if a section says there is no new content this issue, check time filtering and previous-issue deduplication before assuming the crawler is broken
5. treat page-structure errors and `debug/` diagnostics as real crawler issues; treat `no new items in the current window` as a normal outcome

## Known Issues

- some sites do not expose usable timestamps on list pages, so the program still has to open detail pages before filtering
- complex secondary verification may still require manual browser intervention
- DOCX export still depends on local `pandoc`
