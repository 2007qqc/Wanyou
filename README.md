# Wanyou

清华大学物理系“万有预报”自动生成项目。

项目会抓取校内网站、公众号和物理系学术报告页面，经 LLM 筛选、压缩和排版后生成 Markdown、H5 HTML，并可自动保存到秀米草稿。当前支持 Windows 和 macOS。

## 用 wanyou-forecast 一次性全量生成万有预报

`wanyou-forecast` 是本仓库内置的 Claude Code skill（位于 `skills/wanyou-forecast/`），作为**一次性全量生成**一期万有预报的入口：5 个来源模块（公众号、物理系学术报告、图书馆、新清华学堂、教务+家园网）由子代理**并行**爬取，随后合并 raw → LLM 打分排序并合成 → 导出 H5 → 自动保存到秀米草稿，一次跑通整条发布链路，无需手动分步执行。

在 Claude Code 中调用：

```
/wanyou-forecast
```

skill 会自行编排多代理并行和各阶段脚本，生成过程中保持浏览器登录态即可。

### 装进其他 agent 工具（Codex / Copilot / Cursor …）

`wanyou-forecast` 遵循 Agent Skills 开放标准（`SKILL.md` 含 `name` / `description` frontmatter），同一份 skill 可直接放进各支持该标准的工具本地目录，无需改写。源文件在仓库 `skills/wanyou-forecast/`。

各工具读取 skills 的目录：

| 工具 | 个人级（全局，所有项目可用） | 项目级（仅当前仓库） |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| OpenAI Codex | `~/.codex/skills/` 或 `~/.agents/skills/` | `.agents/skills/` |
| GitHub Copilot CLI | `~/.copilot/skills/` 或 `~/.agents/skills/` | `.github/skills/`、`.claude/skills/`、`.agents/skills/` |
| Cursor | `~/.cursor/skills/` 或 `~/.agents/skills/` | `.cursor/skills/`、`.agents/skills/`（兼容 `.claude/skills/`、`.codex/skills/`） |

**方式 A：复制**（简单，但 skill 更新后需手动同步）

```powershell
# Windows
Copy-Item -Recurse skills/wanyou-forecast "$HOME\.claude\skills\wanyou-forecast"   # Claude Code
Copy-Item -Recurse skills/wanyou-forecast "$HOME\.codex\skills\wanyou-forecast"    # Codex
Copy-Item -Recurse skills/wanyou-forecast "$HOME\.copilot\skills\wanyou-forecast"  # Copilot CLI
Copy-Item -Recurse skills/wanyou-forecast "$HOME\.cursor\skills\wanyou-forecast"   # Cursor
```

```bash
# macOS / Linux
cp -r skills/wanyou-forecast ~/.claude/skills/wanyou-forecast
cp -r skills/wanyou-forecast ~/.codex/skills/wanyou-forecast
cp -r skills/wanyou-forecast ~/.copilot/skills/wanyou-forecast
cp -r skills/wanyou-forecast ~/.cursor/skills/wanyou-forecast
```

**方式 B：软链接**（推荐，单一来源，仓库 `git pull` 后自动同步）

```powershell
# Windows（Junction 目录联接无需管理员权限；SymbolicLink 需开发者模式）
$target = (Resolve-Path skills/wanyou-forecast).Path
New-Item -ItemType Junction -Path "$HOME\.claude\skills\wanyou-forecast"  -Target $target
New-Item -ItemType Junction -Path "$HOME\.codex\skills\wanyou-forecast"   -Target $target
New-Item -ItemType Junction -Path "$HOME\.copilot\skills\wanyou-forecast" -Target $target
New-Item -ItemType Junction -Path "$HOME\.cursor\skills\wanyou-forecast"  -Target $target
```

```bash
# macOS / Linux
ln -s "$(pwd)/skills/wanyou-forecast" ~/.claude/skills/wanyou-forecast
ln -s "$(pwd)/skills/wanyou-forecast" ~/.codex/skills/wanyou-forecast
ln -s "$(pwd)/skills/wanyou-forecast" ~/.copilot/skills/wanyou-forecast
ln -s "$(pwd)/skills/wanyou-forecast" ~/.cursor/skills/wanyou-forecast
```

装完后：

- **Claude Code**：直接输入 `/wanyou-forecast`。
- **Copilot CLI**：先 `/skills reload`（或 `copilot skill add skills/wanyou-forecast`），再输入 `/wanyou-forecast`。
- **Cursor**：输入 `/wanyou-forecast`。
- **Codex**：重启 Codex 后在新会话中描述任务，或直接提 `/wanyou-forecast` 触发。

## 功能概览

- 抓取教务通知、家园网、图书馆、新清华学堂、物理系学术报告和公众号信息
- 统一身份认证：教务和家园网共享一次登录，会自动等待用户完成二次认证
- LLM 筛选、摘要压缩、栏目导语和最终富文本清洗
- 输出 Markdown、HTML、可选 DOCX 和浏览器 Agent payload
- 支持自动填充并保存秀米草稿，保存后保留浏览器供用户继续编辑

## 工作流

```text
网页和公众号来源
  -> raw Markdown
  -> LLM 评测重要性的 ranked raw
  -> 清洗、选优、合成万有预报本地 Markdown 和 HTML
  -> 秀米草稿
```

输入来源分三类：

- 需要统一身份认证的网页：教务通知、家园网信息。
- 不需要统一身份认证的网页：图书馆、新清华学堂、物理系学术报告等公开页面。
- 需要 API 抓取的公众号：通过 `WECHAT_PUBLIC_API_KEY` 获取公众号文章列表和正文摘要。

`raw` 尽量保留抓取到的原始信息；`ranked raw` 用 LLM 从物理系本科生视角评估重要性并排序；最终合成阶段只选择高优先级内容，做最后一层清洗和排版，输出本地 `.md`、`.html`，也可以继续送到秀米生成草稿。

## 环境配置

基础要求：

- Python 3.10+
- Windows: Microsoft Edge
- macOS: 推荐 Google Chrome，也支持 Microsoft Edge 和 Safari
- DOCX 导出需要额外安装 `pandoc`

安装依赖：

```bash
python -m pip install -r requirements.txt
python -m pip install PyYAML
```

macOS 推荐配置：

```bash
bash scripts/setup_macos.sh
source .venv/bin/activate
```

### 快速开始

项目在启动时自动读取项目根目录的 `.env`，无需手动 `export`。

```bash
cp .env.example .env
```

核心配置：

| 变量 | 必需 | 用途 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | **是** | LLM API key |
| `WANYOU_USERNAME` | 登录时需要 | 统一身份认证用户名（清华学号） |
| `WANYOU_PASSWORD` | 登录时需要 | 统一身份认证密码 |
| `OCR_SPACE_API_KEY` | OCR 时需要 | 图片文字识别 API key |
| `WECHAT_PUBLIC_API_KEY` | 抓取公众号时需要 | 公众号文章 API key，来自 `down.mptext.top` |
| `WANYOU_SELENIUM_BROWSER` | 否 | 浏览器：macOS 默认 `chrome`，Windows 默认 `edge`，也支持`safari` |

`cp .env.example .env` 后编辑填入 key 即可运行：

```bash
# 公开来源（免登录）烟测
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --public-only --skip-docx

# 完整运行（含统一身份认证）
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --skip-docx
```

完整环境变量参考见[高级调试→环境变量参考](#环境变量参考)。`.env` 不会提交到 Git。

### Safari

Safari 使用系统自带 `safaridriver`。首次使用前：

```bash
safaridriver --enable
```

然后打开 Safari：

1. `Safari > 设置 > 高级`，勾选“在菜单栏中显示开发菜单”。
2. 菜单栏进入 `开发`，勾选“允许远程自动化 / Allow Remote Automation”。

Safari 不支持 Chromium 的独立 profile、headless 和 detach 参数，因此登录态和窗口行为使用系统 Safari 自身的自动化能力。遇到兼容问题时建议切回 Chrome。

## 常用命令

公开来源烟测：

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --public-only --skip-docx
```

完整运行，包括统一身份认证来源：

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --skip-docx
```

生成 ranked raw，用于审稿和排查筛选结果：

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --ranked-raw
```

生成最终富文本：

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --todo-richtext --skip-docx
```

从零生成并保存到秀米草稿（标题自动取 `万有预报 | {最高分条目标题}`，也可 `--title` 手动指定）：

```bash
python scripts/run_wanyou_to_xiumi_draft.py --with-login --skip-docx
```

使用已有 `.html + .md` 保存到秀米草稿：

```bash
python scripts/publish_xiumi_draft.py output/xxx/wanyou_xxx.html --markdown output/xxx/wanyou_xxx.md --title "万有预报"
```

使用最新一次生成的 `.html + .md` 保存到秀米草稿：

```bash
LATEST=$(ls -td --color=never output/20*/ | head -1) && python scripts/publish_xiumi_draft.py ${LATEST}wanyou_*.html --markdown ${LATEST}wanyou_$(basename ${LATEST%/}).md --title "万有预报"
```

只填充秀米、不点击保存：

```bash
python scripts/publish_xiumi_draft.py output/xxx/wanyou_xxx.html --markdown output/xxx/wanyou_xxx.md --dry-run
```

## 秀米草稿

秀米保存流程会：

- 先打开”我的秀米/工作台”并确认登录状态；如果未登录，浏览器会直接暴露给用户在页面完成登录，登录后回终端按回车继续
- 从“我的秀米”页面点击新建图文，不在登录前直接打开 `paper/for/new`
- 优先读取 Markdown，转换为适合秀米的富文本 HTML
- 按“文字 -> 图片 -> 排版”的顺序写入：先写入正文文字和图片占位，避免登录或图库操作打断正文；再打开“我的图库/上传图片(无水印)”上传正文图片，按原始 HTML 图片顺序匹配秀米素材 URL；最后把图片 URL 回填到 HTML 中并重新应用正文排版
- `XIUMI_IMAGE_MODE=upload` 是默认推荐模式；本地图片会优先上传，`data:image/base64` 内联图会后置，避免单张内联图 COS 失败阻断全部图片
- 默认尝试将项目根目录的 `badge.png` 设为草稿封面
- 点击保存并输出 `xiumi_draft_url`
- 保存后保留浏览器，用户可继续在秀米编辑；确认已保存后回到命令行按回车，程序关闭浏览器并结束

自定义或关闭封面：

```bash
python scripts/publish_xiumi_draft.py output/xxx/wanyou_xxx.html --markdown output/xxx/wanyou_xxx.md --cover path/to/cover.png
python scripts/publish_xiumi_draft.py output/xxx/wanyou_xxx.html --markdown output/xxx/wanyou_xxx.md --cover ""
```

从零生成脚本对应参数是 `--xiumi-cover`：

```bash
python scripts/run_wanyou_to_xiumi_draft.py --with-login --skip-docx --xiumi-cover badge.png
```

如需保留固定浏览器 profile，可加：

```bash
python scripts/publish_xiumi_draft.py output/xxx/wanyou_xxx.html --markdown output/xxx/wanyou_xxx.md --profile-dir output/selenium_cache/my-xiumi-profile
python scripts/run_wanyou_to_xiumi_draft.py --with-login --skip-docx --xiumi-profile-dir output/selenium_cache/my-xiumi-profile
```

## 微信公众号草稿箱

项目仍保留直接保存到微信公众号草稿箱的预留功能。当前主线建议先走秀米草稿；公众号草稿接口适合后续需要直接对接公众号后台时使用。

已有 `.html + .md` 输出时：

```bash
python scripts/publish_wechat_draft.py output/xxx/wanyou_xxx.html --markdown output/xxx/wanyou_xxx.md --cover badge.png --title "万有预报"
```

只构建并检查 payload，不调用微信接口：

```bash
python scripts/publish_wechat_draft.py output/xxx/wanyou_xxx.html --markdown output/xxx/wanyou_xxx.md --cover badge.png --dry-run
```

Windows 端也保留了一键脚本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_wanyou_to_wechat_draft.ps1 -WithLogin -SkipDocx -Cover badge.png
```

正式保存需要公众号官方后台的 AppID 和 AppSecret，并且公众号后台需要配置当前机器出口 IP 白名单。它们和用于抓取公众号文章的 `WECHAT_PUBLIC_API_KEY` 不是同一个 key。

## 单模块调试

单模块输出位于 `output/module_<modules>_<timestamp>/`。

```bash
python scripts/run_wanyou_module.py wechat --md-only
python scripts/run_wanyou_module.py physics --raw-only --md-only
python scripts/run_wanyou_module.py public --with-richtext
python scripts/run_wanyou_module.py login --raw-only --md-only
```

如果只想把已有 Markdown 导出为 HTML：

```bash
python skills/wanyou-richtext-export/scripts/run_wanyou_richtext_export.py output/xxx/wanyou_xxx.md --skip-agent-payload
```

## 输出目录

完整流程输出到 `output/<timestamp>/`。

常见文件：

- `*_raw.md`：爬虫原始 Markdown
- `*_ranked_raw.md`：LLM 打分排序后的 raw
- `*_todo_selected_raw.md`：最终富文本候选条目
- `*.md`：最终 Markdown
- `*.html`：H5 富文本预览
- `*_agent.json`：Browser Agent payload
- `debug/`：登录、页面结构和筛选调试信息

## 运行说明

- 统一身份认证会打开可见浏览器。若需要二次认证，用户在浏览器中完成后程序会自动继续，无需回终端按回车。
- `--ranked-raw` 只做本地规则格式整理和 LLM 打分，不做 LLM 正文清洗或摘要压缩。
- 当前 LLM 正文清洗只保留最终富文本合成前的一层，以减少过度清洗、加速运行并节省 token。
- 物理系学术报告会保留原网页中的报告时间、地点、报告人和内容摘要；最终富文本清洗会跳过该版块，避免原始摘要被洗掉。
- DOCX 导出失败时，优先检查本机是否安装 `pandoc`。

## 参考文件

- 配置入口：[config.py](./config.py)
- 物理系本科生偏好模板：[tendency.md](./tendency.md)
- Agent pipeline 说明：[AGENTS.md](./AGENTS.md)

## 高级调试

复现某一天的筛选结果：

```bash
export WANYOU_RUN_DATE="2026-04-20"
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --ranked-raw
```

`WANYOU_RUN_DATE` 只影响日期解析和时效筛选，输出目录仍按真实运行时间命名。

常用 debug 文件：

- `output/<timestamp>/debug/filter_decisions.jsonl`：逐条筛选记录。
- `output/<timestamp>/debug/filter_decisions_summary.json`：筛选汇总。
- `output/<timestamp>/debug/*.html` / `*.txt`：登录、页面结构和选择器快照。

公众号抓取常见错误：

- `ret=-1`：API 认证失败，检查 `WECHAT_PUBLIC_API_KEY`。
- `ret=401` / `ret=403`：API 无权限或 key 权限不足。
- `ret=200003` / `invalid session`：API 会话无效或过期，需要更新 key/session。

### 环境变量参考

#### 正文图片与 OCR

| 变量 | 用途 |
| --- | --- |
| `RAW_COLLECTION_KEEP_IMAGES` | raw/ranked raw 阶段保留并下载正文图片，默认开启 |
| `MYHOME_IMAGE_OCR_ENABLED` | 家园网图片启用 OCR 文字识别，默认开启 |
| `MYHOME_IMAGE_OCR_KEEP_IMAGE` | 家园网图片 OCR 后保留原图，默认开启 |
| `MYHOME_IMAGE_OCR_API_KEY_ENV` | 家园网 OCR 读取哪个 API key 变量，默认 `OCR_SPACE_API_KEY` |
| `MYHOME_IMAGE_OCR_SPACE_URL` | 家园网 OCR 接口地址，默认 `https://api.ocr.space/parse/image` |
| `WECHAT_OCR_SPACE_URL` | 公众号公开图片 URL OCR 接口，默认 `https://api.ocr.space/parse/imageurl` |
| `IMAGE_LLM_PROVIDER` | 识图大模型 provider，可选 `openai`、`gemini` 等 |
| `IMAGE_LLM_BASE_URL` | 识图大模型兼容接口地址 |
| `IMAGE_LLM_MODEL` | 识图大模型名称 |
| `IMAGE_LLM_API_KEY_ENV` | 识图大模型读取哪个 API key 变量 |
| `OPENAI_API_KEY` | 识图大模型 API key（当 `IMAGE_LLM_API_KEY_ENV=OPENAI_API_KEY` 时使用） |
| `WECHAT_IMAGE_LLM_ENABLED` | 公众号图片是否使用识图大模型判断图片类型，默认开启 |
| `OCR_VISION_LLM_ENABLED` | 是否启用识图大模型 OCR |
| `OCR_VISION_LLM_MODE` | 识图 OCR 模式：`fallback`（OCR.Space 兜底）、`prefer`（优先）或 `only`（唯一） |
| `OCR_VISION_LLM_PROVIDER` | OCR 识图模型 provider，例如 `zhipuai` |
| `OCR_VISION_LLM_BASE_URL` | OCR 识图模型兼容接口地址 |
| `OCR_VISION_LLM_MODEL` | OCR 识图模型名称，例如 `glm-4v-flash` |
| `OCR_VISION_LLM_API_KEY_ENV` | OCR 识图模型读取哪个 API key 变量 |

#### 秀米草稿

| 变量 | 用途 |
| --- | --- |
| `XIUMI_HOME_URL` | 秀米"我的秀米/工作台"入口，默认 `https://xiumi.us/studio/v5?lang=zh_CN#/` |
| `XIUMI_IMAGE_MODE` | 正文图片处理：`upload`（推荐）、`auto`、`inline` 或 `omit` |
| `XIUMI_MAX_INLINE_IMAGE_HTML_CHARS` | `auto` 模式下允许内联图片后的最大正文体积，默认 `900000` |
| `XIUMI_IMAGE_UPLOAD_MAX_FAILURES` | 开头连续几张图片拿不到秀米素材 URL 后判定上传链路异常并降级，默认 `3` |
| `XIUMI_IMAGE_UPLOAD_RETRIES` | 单张图片上传失败后的轻量重试次数，默认 `2` |
| `XIUMI_IMAGE_UPLOAD_BATCH_SIZE` | 秀米图库批量上传每组图片数量，默认 `6` |
| `XIUMI_IMAGE_UPLOAD_STALL_SECONDS` | 上传状态长时间无变化时的卡死保护，默认 `180` |

#### LLM 模型配置

| 变量 | 用途 |
| --- | --- |
| `LLM_PROVIDER` | LLM provider，可选 `deepseek`、`openai`、`zhipuai`、`gemini`，默认 `deepseek` |
| `LLM_MODEL` | 全局默认 LLM 模型，默认 `deepseek-v4-flash` |
| `LLM_BASE_URL` | LLM 兼容接口地址 |
| `LLM_API_KEY_ENV` | 全局 LLM 读取哪个 API key 变量（各 provider 有各自的默认 key 变量） |
| `FINAL_MARKDOWN_LLM_CLEAN_ENABLED` | 最终 Markdown 是否经 LLM 清洗排版，默认开启 |

各步骤可使用独立模型覆盖全局 `LLM_MODEL`，不设置时回退到 `LLM_MODEL`：

| 变量 | 用途 |
| --- | --- |
| `DECIDER_LLM_MODEL` | 信息是否值得保留的决策模型 |
| `WECHAT_SUMMARY_LLM_MODEL` | 公众号文章摘要模型 |
| `PHYSICS_EXTRACT_LLM_MODEL` | 物理系学术报告信息提取模型 |
| `RAW_RANKING_LLM_MODEL` | 原始信息重要性排序模型 |
| `SYNTHESIS_LLM_MODEL` | 最终万有预报合成模型 |
| `MARKDOWN_CLEAN_LLM_MODEL` | 正文 Markdown 清洗模型 |

#### 运行行为控制

| 变量 | 用途 |
| --- | --- |
| `WANYOU_DOTENV_OVERRIDE` | 设为 `0` 时系统环境变量优先于 `.env`，默认覆盖 |
| `WANYOU_ENV_FILE` | 指定其他 env 文件路径 |
| `WANYOU_RUN_DATE` | 模拟某一天的日期（`YYYY-MM-DD`），仅影响时效筛选 |
