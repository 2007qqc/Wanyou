# Wanyou 爬虫工具

## 简介
该项目用于抓取清华大学相关网站的通知信息，并输出为 Markdown/Word 文档；另提供公众号公开历史文章抓取脚本（不登录、不扫码）。

## 依赖
建议 Python 3.9+

必需依赖：
- selenium
- webdriver_manager
- requests
- html2text
- pypandoc

你需要自行安装对应浏览器与驱动（Edge），并保证 `pypandoc` 可用。

## 配置（config.py）
所有可调参数已集中到 `/Users/jameslee/Documents/Projects/Wanyou/config.py`：

**登录凭据**
- 运行时从命令行输入（不再写入配置文件）

**Selenium**
- `HEADLESS`
- `PAGE_LOAD_TIMEOUT`
- `WAIT_TIMEOUT`
- `SLEEP_SECONDS`

**时间窗口**
- `DAYS_WINDOW_INFO`
- `DAYS_WINDOW_MYHOME`
- `DAYS_WINDOW_LIB`
- `HALL_RECENT_DAYS`
- `LIB_EVENT_YEAR_ROLL_DAYS`

**URL**
- `URL_INFO`
- `URL_MYHOME`
- `URL_LIB_NOTICE`
- `URL_LIB_EVENT`
- `URL_HALL_PAGES`

**筛选/排除规则**
- `MYHOME_NO_CONSIDER`
- `LIB_NO_CONSIDER`
- `LIB_CONSIDER`
- `HALL_NO_CONSIDER`

**myhome 图片 OCR**
- `MYHOME_IMAGE_OCR_ENABLED`
- `MYHOME_IMAGE_OCR_KEEP_IMAGE`
- `MYHOME_IMAGE_OCR_SPACE_URL`
- `MYHOME_IMAGE_OCR_API_KEY_ENV`
- `MYHOME_IMAGE_OCR_LANGUAGE`
- `MYHOME_IMAGE_OCR_ENGINE`
- `MYHOME_IMAGE_OCR_TIMEOUT_SECONDS`

**输出**
- `OUTPUT_DIR`
- `OUTPUT_NAME_PREFIX`
- `IMAGES_DIR_PREFIX`
- `PANDOC_RESOURCE_PATH_TEMPLATE`

**公众号抓取**
- `WECHAT_PUBLIC_API_BASE_URL`
- `WECHAT_PUBLIC_API_KEY_ENV`
- `WECHAT_ACCOUNT_KEYWORD`
- `WECHAT_FAKEID`
- `WECHAT_ARTICLE_SIZE`
- `WECHAT_DAYS_LIMIT`
- `WECHAT_MAIN_RECENT_DAYS`
- `WECHAT_OUTPUT_FORMAT`

**LLM 自动决策（yes/no）**
- `LLM_ENABLED`
- `LLM_PROVIDER`（`openai` / `zhipuai`）
- `LLM_MODEL`
- `LLM_API_KEY_ENV`（通过环境变量提供密钥）
- `LLM_BASE_URL`
- `LLM_TIMEOUT_SECONDS`
- `LLM_LOG_PATH`
- `LLM_FORCE_YES_KEYWORDS`
- `LLM_FORCE_NO_KEYWORDS`
- `LLM_SYSTEM_PROMPT`

## 运行方式
### 抓取校内通知
```bash
python main.py
```
运行时会提示输入用户名/密码（不回显密码）。
输出：
- `wanyou_<timestamp>.md`
- `wanyou_<timestamp>.docx`
- 输出目录：`./output/<timestamp>/`
  - `wanyou_<timestamp>.md`
  - `wanyou_<timestamp>.docx`
  - `images/`（正文图片与学堂海报）
  - `llm_decisions.jsonl`（若开启）

`main.py` 现在会额外追加“公众号信息（最近7天）”章节（可通过 `WECHAT_MAIN_RECENT_DAYS` 调整）。

若要把 myhome 正文图片转成文字（图片通常是文字截图），请在 `config.py` 打开：
```python
MYHOME_IMAGE_OCR_ENABLED = True
```
并设置 OCR.Space Key（默认读取 `OCR_SPACE_API_KEY`）：
```bash
export OCR_SPACE_API_KEY="你的apikey"
```
说明：
- 识别成功时，会把 Markdown 图片替换为 `[图片文字] ...`。
- `MYHOME_IMAGE_OCR_KEEP_IMAGE = True` 时，保留原图并在下方追加文字。
- 若图片识别为空，不会输出“无内容”占位，保留原图片。

### 自动回答是否拷贝（LLM）
默认使用智谱（ChatGLM），也支持 OpenAI 兼容接口。

智谱（SDK）示例：
```bash
export ZHIPUAI_API_KEY="你的key"
```

OpenAI 示例（需要环境变量）：
```bash
export OPENAI_API_KEY="你的key"
```

在 `config.py` 中设置：
- `LLM_PROVIDER = "zhipuai"` 或 `"openai"`
- `LLM_MODEL` 选择对应模型（智谱推荐 `glm-4`）
- `LLM_API_KEY_ENV` 设置为 `ZHIPUAI_API_KEY` 或 `OPENAI_API_KEY`
- `LLM_BASE_URL`（仅 OpenAI/兼容接口需要）：
  - OpenAI: `https://api.openai.com/v1`

`LLM_SYSTEM_PROMPT` 用于固定“哪些内容应该返回 YES”，
`LLM_FORCE_YES_KEYWORDS` / `LLM_FORCE_NO_KEYWORDS` 则用于**硬规则**优先判定。

### 抓取公众号公开历史文章
先在 `config.py` 里设置以下字段（使用 `down.mptext.top` API）：
- `WECHAT_PUBLIC_API_BASE_URL`
- `WECHAT_ACCOUNT_KEYWORD`（或直接设置 `WECHAT_FAKEID`）

如接口需要鉴权，再设置 API Key 环境变量（作为请求头 `X-Auth-Key`）：
```bash
export WECHAT_PUBLIC_API_KEY="你的key"
```

若开启 OCR，再设置 OCR.Space API Key：
```bash
export OCR_SPACE_API_KEY="你的apikey"
```

然后运行：
```bash
python wechat_public.py
```
输出：
- `wechat_<timestamp>.md`（默认）
- 或 `wechat_<timestamp>.json`（当 `WECHAT_OUTPUT_FORMAT="json"`）

**接口对应关系**
1. `/account?keyword=...`：根据公众号名称查询账号信息（拿到 `fakeid`）。
2. `/article?fakeid=...`：获取历史文章列表。
3. `/download?url=...&format=html`：下载单篇正文 HTML。

**正文抓取、OCR 与筛选配置**
- 脚本会对每条文章请求正文页面；`WECHAT_FETCH_CONTENT` 仅控制 md 是否写入正文。
- `WECHAT_OCR_ENABLED = True` 时会提取正文图片文字，写入内容中的 `[图片文字 N]`。
- OCR 使用 OCR.Space GET 接口：`WECHAT_OCR_SPACE_URL`（默认 `/parse/imageurl`）。
- `WECHAT_OCR_SPACE_API_KEY_ENV` 指定 API Key 环境变量名（默认 `OCR_SPACE_API_KEY`）。
- 可选参数：`WECHAT_OCR_SPACE_LANGUAGE`、`WECHAT_OCR_SPACE_IS_OVERLAY_REQUIRED`、`WECHAT_OCR_SPACE_DETECT_ORIENTATION`、`WECHAT_OCR_SPACE_IS_TABLE`、`WECHAT_OCR_SPACE_ENGINE`。
- `WECHAT_OCR_MAX_IMAGES_PER_ARTICLE = 0` 表示每篇文章 OCR 全部图片。
- 可选开启图片 LLM 分类：`WECHAT_IMAGE_LLM_ENABLED = True`。判定为 `TABLE` 或 `QRCODE` 时，正文保留原图（Markdown 图片）；其他类型继续写 OCR 文字。
- 图片 LLM 默认复用 `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY_ENV`，也可用 `WECHAT_IMAGE_LLM_BASE_URL`、`WECHAT_IMAGE_LLM_MODEL`、`WECHAT_IMAGE_LLM_API_KEY_ENV` 覆盖。
- `WECHAT_FILTER_MD_WITH_LLM = True` 时，写 md 前会做 YES/NO 决策；json 仍保留全量。
- `WECHAT_FILTER_FALLBACK_KEEP = True` 表示 LLM 失败时默认保留。
- `WECHAT_ARTICLE_SIZE` 控制 `/article` 接口请求的文章数量，`WECHAT_MAX_ARTICLES` 控制最终保留数量（0 表示不限制）。
- `WECHAT_DAYS_LIMIT` 用于独立运行 `wechat_public.py` 时的时间窗口过滤（0 表示不过滤）。
- 若 OCR 后图片无文字，正文中不会输出“未识别”占位。

## 常见问题
1. 登录失败：确认 `USERNAME`/`PASSWORD` 是否正确，并检查 VPN/网络环境。
2. 驱动问题：确保 Edge 驱动与浏览器版本匹配。
3. 公众号抓取失败：优先检查 `WECHAT_PUBLIC_API_KEY`、`WECHAT_ACCOUNT_KEYWORD/WECHAT_FAKEID` 是否正确，以及 API 可用性。

---

# Wanyou Crawler

## Overview
This project crawls several Tsinghua University sites and exports results to Markdown/Word. It also provides a public-history WeChat official account crawler (no login, no QR scan).

## Requirements
Recommended Python 3.9+

Required packages:
- selenium
- webdriver_manager
- requests
- html2text
- pypandoc

You must install Edge and ensure the driver is available. `pypandoc` must be functional.

## Configuration (config.py)
All tunable parameters live in `/Users/jameslee/Documents/Projects/Wanyou/config.py`.

See the Chinese section above for the full list.

## Usage
### Campus notices
```bash
python main.py
```
Outputs:
- `wanyou_<timestamp>.md`
- `wanyou_<timestamp>.docx`
- image folders (`./images_*`, including inline images and hall posters)

`main.py` now appends a WeChat section for recent 7 days (configurable by `WECHAT_MAIN_RECENT_DAYS`).

### WeChat public history
Configure these fields in `config.py` (using `down.mptext.top` API):
- `WECHAT_PUBLIC_API_BASE_URL`
- `WECHAT_ACCOUNT_KEYWORD` (or set `WECHAT_FAKEID` directly)

If the API requires auth, set API key env var for `X-Auth-Key`:
```bash
export WECHAT_PUBLIC_API_KEY="your_key"
```

If OCR is enabled, set OCR.Space API key:
```bash
export OCR_SPACE_API_KEY="your_apikey"
```

Then run:
```bash
python wechat_public.py
```
Outputs:
- `wechat_<timestamp>.md` (default)
- or `wechat_<timestamp>.json` (when `WECHAT_OUTPUT_FORMAT="json"`)

**API mapping**
1. `/account?keyword=...`: resolve account and get `fakeid`.
2. `/article?fakeid=...`: fetch article list.
3. `/download?url=...&format=html`: fetch article HTML content.

**Content, OCR & Filtering Options**
- The script fetches each article detail page; `WECHAT_FETCH_CONTENT` only controls whether md writes full content.
- Set `WECHAT_OCR_ENABLED = True` to OCR images and inject `[图片文字 N]` in content.
- OCR uses OCR.Space GET endpoint via `WECHAT_OCR_SPACE_URL`.
- Set key env name with `WECHAT_OCR_SPACE_API_KEY_ENV` (default `OCR_SPACE_API_KEY`).
- Optional OCR params: `WECHAT_OCR_SPACE_LANGUAGE`, `WECHAT_OCR_SPACE_IS_OVERLAY_REQUIRED`, `WECHAT_OCR_SPACE_DETECT_ORIENTATION`, `WECHAT_OCR_SPACE_IS_TABLE`, `WECHAT_OCR_SPACE_ENGINE`.
- `WECHAT_OCR_MAX_IMAGES_PER_ARTICLE = 0` means OCR all images in each article.
- Optional image LLM classifier: set `WECHAT_IMAGE_LLM_ENABLED = True`. If classified as `TABLE` or `QRCODE`, the original image is kept in Markdown.
- Image LLM uses `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY_ENV` by default, overridable with `WECHAT_IMAGE_LLM_BASE_URL`, `WECHAT_IMAGE_LLM_MODEL`, `WECHAT_IMAGE_LLM_API_KEY_ENV`.
- `WECHAT_FILTER_MD_WITH_LLM = True` filters md by YES/NO decision; json keeps full records.
- `WECHAT_FILTER_FALLBACK_KEEP = True` means keep items when decision API fails.
- `WECHAT_ARTICLE_SIZE` controls list size requested from `/article`; `WECHAT_MAX_ARTICLES` limits final kept items (0 means no limit).
- `WECHAT_DAYS_LIMIT` applies when running `wechat_public.py` standalone (0 means no date filter).
- If an image has no OCR text, no placeholder line will be emitted.

## FAQ
1. Login failure: check `USERNAME`/`PASSWORD` and VPN/network.
2. Driver issues: make sure Edge driver matches the browser version.
3. WeChat crawl fails: check `WECHAT_PUBLIC_API_KEY`, `WECHAT_ACCOUNT_KEYWORD/WECHAT_FAKEID`, and API availability first.
4. LLM 无响应：检查 API Key 环境变量、网络、模型名与 base URL 是否匹配。
