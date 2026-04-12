# Wanyou

清华大学物理系“万有预报”自动生成项目。

本项目用于从校内网站、公众号和物理系学术报告页面抓取信息，经过 LLM 筛选、压缩和排版后，生成 Markdown、H5 HTML 和可选的 Browser Agent payload。

## 功能概览

当前流程支持：

- 教务通知、家园网、图书馆、新清华学堂、物理系学术报告等来源抓取
- 清华统一身份认证登录，教务和家园网共享一次浏览器会话
- 二次认证人工接管：程序弹出 Edge，用户完成认证后回到终端继续
- 公众号 API 抓取与摘要输出
- LLM 辅助筛选、正文清洗、摘要压缩和栏目导语生成
- Markdown、H5 HTML、Browser Agent payload 输出
- 单模块测试运行，便于只测试公众号或某一个网站爬虫

## 环境要求

- Python 3.10+
- Microsoft Edge
- Edge WebDriver
- 如需 DOCX 导出，还需要本机安装 `pandoc`

安装依赖：

```powershell
python -m pip install -r requirements.txt
python -m pip install PyYAML
```

## 快速运行

只运行公开来源，适合烟测：

```powershell
python skills\wanyou-full-run\scripts\run_wanyou_full_run.py --public-only --skip-docx
```

运行完整流程，包括统一身份认证来源：

```powershell
python skills\wanyou-full-run\scripts\run_wanyou_full_run.py --with-login
```

跳过公众号，只调试校内网站：

```powershell
python skills\wanyou-full-run\scripts\run_wanyou_full_run.py --with-login --skip-wechat --skip-docx
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

???????????

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

## 公众号 API 环境变量
公众号抓取使用 `down.mptext.top` API，不直接登录微信。程序读取环境变量：

```text
WECHAT_PUBLIC_API_KEY
```

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

教务通知和家园网默认使用同一套清华统一身份认证账号密码。程序会打开可见 Edge 浏览器，并尽量只做一次统一认证。

如果进入二次认证：

1. 程序会保留可见 Edge 浏览器窗口。
2. 用户在浏览器中手动完成二次认证。
3. 回到终端按回车。
4. 程序继续抓取教务和家园网。

调试教务和家园网时建议先运行：

```powershell
python scripts\run_wanyou_module.py login --raw-only --md-only
```

## 筛选策略

当前 LLM 筛选重点：

- 只接受生成万有预报前一周内发布的信息。
- 只接受和清华大学物理系本科生直接相关的信息。
- 重点核对时间戳、发布者、面向群体，再结合正文内容判断。
- 研究生会、研究生招生、教师招聘等与物理系本科生关系弱的信息会被排除。
- 公众号按文章发布日期取最新 5 条以内。
- 其他小版块信息过多时，每个版块最多保留 4 条。
- 单条信息会通过 LLM 压缩，控制摘要和正文总篇幅。

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
