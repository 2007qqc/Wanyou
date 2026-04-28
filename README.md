# Wanyou

清华大学物理系“万有预报”自动生成项目。

项目会抓取校内网站、公众号和物理系学术报告页面，经 LLM 筛选、压缩和排版后生成 Markdown、H5 HTML，并可自动保存到秀米草稿。当前支持 Windows 和 macOS。

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
export WANYOU_SELENIUM_BROWSER=chrome
```

macOS 默认使用 `chrome`，Windows 默认使用 `edge`。如需切换浏览器，设置 `WANYOU_SELENIUM_BROWSER` 为 `chrome`、`edge` 或 `safari`。

### 环境变量

| 变量 | 用途 |
| --- | --- |
| `DEEPSEEK_API_KEY` | DeepSeek / LLM API key |
| `WECHAT_PUBLIC_API_KEY` | 公众号文章抓取 API key，来自 `down.mptext.top` |
| `WECHAT_MP_APPID` | 微信公众号官方后台 AppID，用于预留的公众号草稿箱接口 |
| `WECHAT_MP_APPSECRET` | 微信公众号官方后台 AppSecret，用于预留的公众号草稿箱接口 |
| `WANYOU_SELENIUM_BROWSER` | Selenium 浏览器，可选 `chrome`、`edge`、`safari` |

macOS / Linux 当前终端临时设置：

```bash
export DEEPSEEK_API_KEY="your-deepseek-api-key"
export WECHAT_PUBLIC_API_KEY="your-public-api-key"
export WECHAT_MP_APPID="your-official-account-appid"
export WECHAT_MP_APPSECRET="your-official-account-appsecret"
export WANYOU_SELENIUM_BROWSER="chrome"
```

macOS 写入当前用户的 zsh 配置：

```bash
cat >> ~/.zshrc <<'EOF'
export DEEPSEEK_API_KEY="your-deepseek-api-key"
export WECHAT_PUBLIC_API_KEY="your-public-api-key"
export WECHAT_MP_APPID="your-official-account-appid"
export WECHAT_MP_APPSECRET="your-official-account-appsecret"
export WANYOU_SELENIUM_BROWSER="chrome"
EOF

source ~/.zshrc
```

验证 macOS 环境变量是否已生效：

```bash
echo "$DEEPSEEK_API_KEY"
echo "$WECHAT_PUBLIC_API_KEY"
echo "$WECHAT_MP_APPID"
echo "$WECHAT_MP_APPSECRET"
echo "$WANYOU_SELENIUM_BROWSER"
```

Windows PowerShell 临时设置：

```powershell
$env:DEEPSEEK_API_KEY = "your-deepseek-api-key"
$env:WECHAT_PUBLIC_API_KEY = "your-public-api-key"
$env:WECHAT_MP_APPID = "your-official-account-appid"
$env:WECHAT_MP_APPSECRET = "your-official-account-appsecret"
$env:WANYOU_SELENIUM_BROWSER = "edge"
```

Windows 用户级持久设置：

```powershell
[Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", "your-deepseek-api-key", "User")
[Environment]::SetEnvironmentVariable("WECHAT_PUBLIC_API_KEY", "your-public-api-key", "User")
[Environment]::SetEnvironmentVariable("WECHAT_MP_APPID", "your-official-account-appid", "User")
[Environment]::SetEnvironmentVariable("WECHAT_MP_APPSECRET", "your-official-account-appsecret", "User")
[Environment]::SetEnvironmentVariable("WANYOU_SELENIUM_BROWSER", "edge", "User")
```

写入用户级变量后需要重新打开终端或 IDE。

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

从零生成并保存到秀米草稿：

```bash
python scripts/run_wanyou_to_xiumi_draft.py --with-login --skip-docx
```

使用已有 `.html + .md` 保存到秀米草稿：

```bash
python scripts/publish_xiumi_draft.py output/xxx/wanyou_xxx.html --markdown output/xxx/wanyou_xxx.md --title "万有预报"
```

只填充秀米、不点击保存：

```bash
python scripts/publish_xiumi_draft.py output/xxx/wanyou_xxx.html --markdown output/xxx/wanyou_xxx.md --dry-run
```

## 秀米草稿

秀米保存流程会：

- 打开秀米图文编辑器 `paper/for/new`
- 如果未登录，等待用户在浏览器中登录，登录成功后自动继续
- 优先读取 Markdown，转换为内联富文本后写入正文
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

DeepSeek 兼容网关或自定义模型可通过环境变量覆盖：

```bash
export DEEPSEEK_API_KEY="your-deepseek-api-key"
export LLM_BASE_URL="https://your-compatible-endpoint/v1"
export LLM_API_KEY_ENV="DEEPSEEK_API_KEY"
```

公众号抓取常见错误：

- `ret=-1`：API 认证失败，检查 `WECHAT_PUBLIC_API_KEY`。
- `ret=401` / `ret=403`：API 无权限或 key 权限不足。
- `ret=200003` / `invalid session`：API 会话无效或过期，需要更新 key/session。
