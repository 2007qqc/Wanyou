# Wanyou

清华大学物理系“万有预报”自动生成项目。

本项目用于从校内网站、公众号和物理系学术报告页面抓取信息，经过 LLM 筛选、压缩和排版后，生成 Markdown、H5 HTML 和可选的 Browser Agent payload。

## 功能概览

当前流程支持：

- 教务通知、家园网、图书馆、新清华学堂、物理系学术报告等来源抓取
- 清华统一身份认证登录，教务和家园网共享一次浏览器会话
- 二次认证人工接管：程序弹出浏览器，用户完成认证后会自动继续
- 公众号 API 抓取与摘要输出
- LLM 辅助筛选、正文清洗、摘要压缩和栏目导语生成
- Markdown、H5 HTML、Browser Agent payload 输出
- 单模块测试运行，便于只测试公众号或某一个网站爬虫

## 环境要求

- Python 3.10+
- Windows: Microsoft Edge
- macOS: Google Chrome 或 Microsoft Edge
- Selenium 4 会优先通过 Selenium Manager 自动匹配浏览器驱动
- 如需 DOCX 导出，还需要本机安装 `pandoc`

安装依赖：

```bash
python -m pip install -r requirements.txt
python -m pip install PyYAML
```

### macOS 快速配置

macOS 推荐使用项目虚拟环境和 Chrome：

```bash
bash scripts/setup_macos.sh
source .venv/bin/activate
export WANYOU_SELENIUM_BROWSER=chrome
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --public-only --skip-docx
```

如需 DOCX 导出：

```bash
brew install pandoc
```

浏览器可通过 `WANYOU_SELENIUM_BROWSER` 切换，支持 `chrome` 和 `edge`。macOS 默认使用 `chrome`，Windows 默认使用 `edge`。

## 快速运行

只运行公开来源，适合烟测：

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --public-only --skip-docx
```

运行完整流程，包括统一身份认证来源：

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login
```

跳过公众号，只调试校内网站：

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --skip-wechat --skip-docx
```

生成整体 ranked raw，用于审稿和排查筛选结果：

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --ranked-raw
```

`--ranked-raw` 会爬取各平台信息，不下载图片；只做一周内发布的硬性时效筛选和本地规则格式整理，不做 LLM 正文清洗，也不做摘要压缩。随后 LLM 会按物理系本科生视角为各版块条目打重要性分数并排序，输出 `*_ranked_raw.md`。

兼容旧命令的写法如下；当前行为等价于 `--ranked-raw`，不会触发 LLM 正文清洗：

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --ranked-raw-no-clean
```

该模式输出 `*_ranked_raw_no_clean.md`，适合快速审稿或排查爬虫原始正文。

按 TODO 标准直接生成完整富文本：先生成 ranked raw，再按每类最高分条目挑选 3-5 条，最后输出主题化 Markdown 和 HTML：

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --todo-richtext
```

## 单模块测试命令

下面这些命令主要作为测试和排障使用。每次运行会在 `output/module_<modules>_<timestamp>/` 下生成对应产物。

### 公众号单独测试

生成公众号部分的 Markdown 和 HTML：

```powershell
python scripts\run_wanyou_module.py wechat --with-richtext
```

只生成 Markdown，不生成富文本 HTML：

```powershell
python scripts\run_wanyou_module.py wechat --md-only
```

只看爬虫 raw Markdown，不走 LLM 合成，也不生成 HTML：

```powershell
python scripts\run_wanyou_module.py wechat --raw-only --md-only
```

### 分别测试各模块

```powershell
python scripts\run_wanyou_module.py lib --with-richtext
python scripts\run_wanyou_module.py hall --with-richtext
python scripts\run_wanyou_module.py physics --with-richtext
python scripts\run_wanyou_module.py info --with-richtext
python scripts\run_wanyou_module.py myhome --with-richtext
python scripts\run_wanyou_module.py wechat --with-richtext
```

### 批量测试模块

只测试公开来源：

```powershell
python scripts\run_wanyou_module.py public --with-richtext
```

只测试需要统一身份认证的来源：

```powershell
python scripts\run_wanyou_module.py login --with-richtext
```

测试全部模块：

```powershell
python scripts\run_wanyou_module.py all --with-richtext
```

### 通过 skills 入口测试

`skills/wanyou-campus-crawl` 是对单模块测试脚本的包装，等价于 `scripts/run_wanyou_module.py`：

```powershell
python skills\wanyou-campus-crawl\scripts\run_wanyou_campus_crawl.py wechat --with-richtext
python skills\wanyou-campus-crawl\scripts\run_wanyou_campus_crawl.py public --md-only
python skills\wanyou-campus-crawl\scripts\run_wanyou_campus_crawl.py login --raw-only --md-only
```

## Markdown 转富文本

如果已经有最终 Markdown，可以单独导出 H5 HTML 和 Browser Agent payload：

```powershell
python skills\wanyou-richtext-export\scripts\run_wanyou_richtext_export.py output\xxx\wanyou_xxx.md
```

只导出 HTML：

```powershell
python skills\wanyou-richtext-export\scripts\run_wanyou_richtext_export.py output\xxx\wanyou_xxx.md --skip-agent-payload
```

只导出 Browser Agent payload：

```powershell
python skills\wanyou-richtext-export\scripts\run_wanyou_richtext_export.py output\xxx\wanyou_xxx.md --skip-html
```

如果已有 raw Markdown，可以先单独跑 LLM 筛选和摘要：

```powershell
python skills\wanyou-llm-filter\scripts\run_wanyou_llm_filter.py output\xxx\wanyou_xxx_raw.md
```


## 保存到微信公众号草稿箱

项目提供“只保存草稿、不自动发布”的脚本：

```powershell
python scripts\publish_wechat_draft.py output\xxx\wanyou_xxx.html --cover output\xxx\_theme\badge.png --title "万有预报"
```

建议先 dry-run，确认正文提取和图片路径正常，不实际调用微信接口：

```powershell
python scripts\publish_wechat_draft.py output\xxx\wanyou_xxx.html --dry-run
```

如果要强制指定封面图：
加上封面的dry-run示例：

```powershell
python scripts\publish_wechat_draft.py output\xxx\wanyou_xxx.html --cover output\xxx\_theme\badge.png --dry-run
```

该脚本会：

- 从 H5 HTML 中提取正文片段
- 移除完整网页外壳和脚本样式标签
- 上传正文中的本地图片，并替换为微信图片 URL
- 上传封面图，获取 `thumb_media_id`
- 调用微信公众号草稿箱接口，返回草稿 `media_id`

保存草稿需要公众号官方后台的 AppID 和 AppSecret。它们和用于抓取公众号历史文章的 `WECHAT_PUBLIC_API_KEY` 不是同一个东西。

临时设置：

```powershell
$env:WECHAT_MP_APPID = "your-appid"
$env:WECHAT_MP_APPSECRET = "your-appsecret"
```

持久设置：

```powershell
[Environment]::SetEnvironmentVariable("WECHAT_MP_APPID", "your-appid", "User")
[Environment]::SetEnvironmentVariable("WECHAT_MP_APPSECRET", "your-appsecret", "User")
```

写入后请重新打开 PowerShell 或 IDE 终端，再运行草稿脚本。公众号后台还需要把当前机器出口 IP 加入 IP 白名单，否则获取 `access_token` 可能失败。

安全建议：先保存到草稿箱，在公众号后台人工预览确认后再发布，不建议一开始直接自动发布。

## 保存到秀米草稿

项目现在提供“直接打开秀米图文编辑器、自动填充内容并点击保存”的脚本。
这是浏览器自动化方案：如果你尚未登录秀米，脚本会打开 Edge 并等待你手动登录；登录完成后回到终端按回车，脚本会继续填充正文并保存草稿。

已有 `.html + .md` 输出时，直接推送到秀米：

```powershell
python scripts\publish_xiumi_draft.py output\xxx\wanyou_xxx.html --markdown output\xxx\wanyou_xxx.md --title "万有预报"
```

如果只想检查自动填充效果，不点击保存：

```powershell
python scripts\publish_xiumi_draft.py output\xxx\wanyou_xxx.html --markdown output\xxx\wanyou_xxx.md --dry-run
```

从零开始跑完整万有预报并直接送到秀米：

```bash
python scripts/run_wanyou_to_xiumi_draft.py
```

如需同时抓取统一认证站点：

```bash
python scripts/run_wanyou_to_xiumi_draft.py --with-login
```

默认行为：
- 直接打开秀米图文编辑器 `paper/for/new`
- 优先读取同名 Markdown，将其转换为内联富文本后写入秀米正文
- 若正文中仍引用本地图片，会自动转成 data URL 内嵌，减少秀米端丢图概率
- 点击保存后，若当前地址从 `for/new` 变为正式草稿地址，会在终端输出 `xiumi_draft_url`

当前限制：
- 秀米登录仍需人工完成
- 若秀米改版导致按钮或输入框选择器变化，脚本可能需要重新适配
- 当前实现是“浏览器自动保存草稿”，不是秀米开放 API 对接

## 公众号 API 环境变量
公众号抓取使用 `down.mptext.top` API，不直接登录微信。程序读取环境变量：

```text
WECHAT_PUBLIC_API_KEY
```

### macOS / Linux 临时设置

只对当前终端窗口有效：

```bash
export WECHAT_PUBLIC_API_KEY="your-key"
echo "$WECHAT_PUBLIC_API_KEY"
python scripts/run_wanyou_module.py wechat --md-only
```

如果希望每次打开终端都生效，可以把 `export WECHAT_PUBLIC_API_KEY="your-key"` 写入 `~/.zshrc`。

### 当前 PowerShell 临时设置

只对当前终端窗口有效：

```powershell
$env:WECHAT_PUBLIC_API_KEY = "your-key"
echo $env:WECHAT_PUBLIC_API_KEY
python scripts\run_wanyou_module.py wechat --md-only
```

### 当前用户持久设置

写入当前 Windows 用户环境变量：

```powershell
[Environment]::SetEnvironmentVariable("WECHAT_PUBLIC_API_KEY", "your-key", "User")
```

写入后需要重新打开 PowerShell 或重启 IDE 终端，然后验证：

```powershell
echo $env:WECHAT_PUBLIC_API_KEY
python scripts\run_wanyou_module.py wechat --md-only
```

如果不想重开终端，可以把用户级变量同步到当前会话：

```powershell
$env:WECHAT_PUBLIC_API_KEY = [Environment]::GetEnvironmentVariable("WECHAT_PUBLIC_API_KEY", "User")
echo $env:WECHAT_PUBLIC_API_KEY
```

### 清除或更换 key

临时清除当前会话：

```powershell
Remove-Item Env:WECHAT_PUBLIC_API_KEY -ErrorAction SilentlyContinue
```

清除用户级持久变量：

```powershell
[Environment]::SetEnvironmentVariable("WECHAT_PUBLIC_API_KEY", $null, "User")
```

更换 key：

```powershell
[Environment]::SetEnvironmentVariable("WECHAT_PUBLIC_API_KEY", "new-key", "User")
$env:WECHAT_PUBLIC_API_KEY = [Environment]::GetEnvironmentVariable("WECHAT_PUBLIC_API_KEY", "User")
python scripts\run_wanyou_module.py wechat --md-only
```

### 常见公众号 API 错误

- `ret=-1`：API 认证失败，请检查 `WECHAT_PUBLIC_API_KEY` 是否正确、有效。
- `ret=401` / `ret=403`：API 无权限，请检查 key 权限。
- `ret=200003` 或 `invalid session`：API 会话无效或已过期，需要重新获取有效 session/key，并更新 `WECHAT_PUBLIC_API_KEY`。

## 登录与二次认证

教务通知和家园网默认使用同一套清华统一身份认证账号密码。程序会打开可见浏览器，并尽量只做一次统一认证。

如果进入二次认证：

1. 程序会保留可见浏览器窗口。
2. 用户在浏览器中手动完成二次认证。
3. 程序自动检测登录状态，成功后继续抓取教务和家园网，无需回终端按回车。

调试教务和家园网时建议先运行：

```powershell
python scripts\run_wanyou_module.py login --raw-only --md-only
```


## 筛选策略

万有预报的筛选分为三层：硬性时效判断、面向物理系本科生的相关性判断、版块容量控制。

### 稳定运行日期

默认情况下，程序把本次运行所在日期的 `00:00` 作为统一时效基准，而不使用运行那一刻的小时和分钟。因此同一天内多次生成，内容不会因上午、下午或晚上运行而变化；只会因网站消息本身变化而变化。

如果需要复现某一天的筛选结果，可以临时指定运行日期：

```powershell
$env:WANYOU_RUN_DATE = "2026-04-20"
python skills\wanyou-full-run\scripts\run_wanyou_full_run.py --skip-docx
```

程序仍会使用真实抓取时间命名输出目录；`WANYOU_RUN_DATE` 只影响日期解析和时效筛选。

### 日期与时效判断

程序会尽量提取标题、摘要、正文、OCR 图片文字中的所有显式日期，并按上下文分类：

- `deadline`：截止、报名截止、申请截止、提交截止、截至、报名时间、申请时间等。
- `event`：活动时间、报告时间、讲座时间、举办时间、开始时间、比赛时间等。
- `publish`：发布时间、发布日期、发布等。
- `mentioned`：能识别出日期，但上下文不足以判断用途。

判断优先级如下：

- 如果识别到截止时间，首要看截止时间；截止未过就保留，截止已过就丢弃。
- 如果没有截止时间，但识别到活动、讲座、报告等时间，则看活动是否尚未发生；刚结束 12 小时内也允许保留。
- 如果只识别到发布时间，才用“运行日期前 7 天”作为兜底阈值。
- 如果完全没有可解析日期，程序不会仅因日期缺失丢弃，会交给后续相关性判断。

这意味着“发布时间较早但报名尚未截止”的信息可以保留，而“今天发布但截止时间已过”的信息会被丢弃。

### 相关性与容量控制

当前 LLM 筛选重点：

- 只接受和清华大学物理系本科生直接相关的信息。
- 优先保留课业相关信息，例如选课、排课、调课、调休、考试、培养方案、学籍和教务安排。
- 优先保留学术与培养相关信息，例如校内培养计划、星火计划、SRT、科研训练、讲座、报告和奖助机会。
- 研究生会、研究生招生、教师招聘、研究生或博士生住宿抽签等与物理系本科生关系弱的信息会被排除。
- 其他小版块信息过多时，每个版块最多保留 4 条。
- 公众号经过时效筛选后，最多保留 5 条，并按学生会、青年科协、学生社团、学生公益、其他公众号信息分版块输出。

### Debug 中的日期筛选记录

每次运行会在 `debug/filter_decisions.jsonl` 和 `debug/filter_decisions_summary.json` 记录筛选过程。日期筛选对应的阶段通常是：

- `temporal_filter`：Markdown 合成阶段的统一日期筛选。
- `wechat_temporal_filter`：公众号正文抓取后的日期筛选。

每条记录的 `details.signals` 会展示程序识别到的日期，包括 `kind`、`raw`、`parsed` 和 `context`；`details.basis` 是实际用于判断的日期；`reason` 会显示 `deadline_active`、`deadline_expired`、`event_active`、`event_expired`、`publish_recent` 或 `publish_older_than_cutoff`。


## 当前栏目行为

- `教务通知`：适配新版教务通知页面；需要统一身份认证。
- `家园网信息`：复用统一身份认证会话抓取。
- `图书馆信息`：公开页面抓取。
- `新清华学堂`：公开页面抓取。
- `物理系学术报告`：保留报告时间判断逻辑；如果本期没有新增报告，会按正常空结果处理。
- `公众号信息`：通过 API 抓取最新文章，并输出摘要而不是全文。

## LLM 配置

默认配置在 [config.py](./config.py)：

```python
LLM_ENABLED = True
LLM_PROVIDER = "deepseek"
LLM_MODEL = "deepseek-chat"
```

所有涉及 LLM 的步骤会输出具体进度，例如：

- `等待LLM输出中：正在判断条目是否保留`
- `等待LLM输出中：正在筛选教务通知保留条目`
- `等待LLM输出中：正在压缩单条信息篇幅`
- `等待LLM输出中：正在总结公众号内容`
- `等待LLM输出中：正在提取学术报告字段`

## 输出目录

完整流程会在 `output/<timestamp>/` 生成产物。

单模块测试会在 `output/module_<modules>_<timestamp>/` 生成产物。

常见文件：

- `*_raw.md`：爬虫原始 Markdown
- `*.md`：LLM 合成和主题包装后的 Markdown
- `*.html`：H5 富文本预览
- `*_agent.json`：Browser Agent payload
- `debug/`：登录、页面结构和选择器调试快照

## 推荐使用策略

1. 调试某个来源时，先用 `python scripts\run_wanyou_module.py <module> --raw-only --md-only`。
2. 确认 raw Markdown 正常后，再用 `--with-richtext` 检查最终版式。
3. 公众号失败时，优先检查 `WECHAT_PUBLIC_API_KEY` 和 session 有效性。
4. 教务或家园网失败时，优先看 `debug/` 下的登录与页面快照。
5. DOCX 导出失败时，先检查本机是否安装 `pandoc`，不要优先改爬虫或 Markdown。

# TODO
## 打分raw

现在程序添加了爬取所有未过时、仅经过本地规则格式整理的 raw 信息并让 LLM 打分的功能模块，
目标是向万有预报制作者提供无遗漏、有权重的参考。但是现在LLM分配的打分
尚不符合物理系同学的信息获取偏好。计划让Codex根据下面的“物理系本科生阅读偏好”
信息来修改prompt，每次修改后运行一遍打分raw，检验LLM评分是否符合物理系本科生偏好
并再修改prompt，形成训练循环，直到评分和偏好符合，进入万有预报生成环节。

当前对应指令：

```powershell
python skills\wanyou-full-run\scripts\run_wanyou_full_run.py --with-login --ranked-raw
```

兼容旧命令的写法如下；当前 `--ranked-raw` 默认也不走 LLM 正文清洗：

```powershell
python skills\wanyou-full-run\scripts\run_wanyou_full_run.py --with-login --ranked-raw-no-clean
```

## 新的万有预报生成逻辑

按上一步训练好LLM、生成正确的打分raw后，按先前的信息类型分类，每个类别取3-5个最高分信息作为
万有预报内容，生成富文本。

当前已实现的对应指令：

```powershell
python skills\wanyou-full-run\scripts\run_wanyou_full_run.py --with-login --todo-richtext
```

该指令会：
1. 先生成 ranked raw；
2. 再按类别选出高分条目；
3. 生成最终主题化 Markdown；
4. 导出 HTML 富文本。

尚未实现的部分：
- 将“打分 raw + 富文本 + 秀米草稿”完全压成单条 Python 指令；
- 将秀米草稿保存做成无需人工登录的正式接口方案。

按这个workflow生成一系列新的万有预报快捷指令：

当前已由下面这条指令等价覆盖：

```powershell
python skills\wanyou-full-run\scripts\run_wanyou_full_run.py --with-login --todo-richtext
```

## 物理系本科生偏好
在`tendency.md`中给出了一个模板。

## 已知问题
已处理：LLM 正文清洗现在只保留最终富文本合成前的一层。爬虫落盘、公众号入库和 ranked raw 阶段只做本地规则格式整理，以减少过度清洗、加速运行并节省 token。
