# Wanyou

清华大学物理系“万有预报”自动化生成项目。

项目目标是把“抓取校园信息 -> LLM 筛选与摘要 -> 富文本/H5 导出 -> 浏览器 Agent 填充”串成一条可调试、可拆分、可一键运行的流水线。当前代码按“功能实现完成，外部网络与站点可达性单独处理”的原则组织。

## Current Status

在排除代理、防火墙、校园站点临时不可达等网络问题的前提下，当前仓库已经实现这些能力：

- 校园网站抓取模块
- LLM 筛选与摘要模块
- 富文本 H5 导出模块
- 浏览器 Agent payload 导出模块
- 可拆分的 `skills/` 模块
- 可单次运行的总控入口

当前默认大模型为 DeepSeek：

- `LLM_ENABLED = True`
- `LLM_PROVIDER = "deepseek"`
- `LLM_MODEL = "deepseek-chat"`

## Requirements

- Python 3.10+
- Microsoft Edge
- Edge WebDriver 可用
- 如需 DOCX 备份导出，还需要本地安装 `pandoc`

Python 依赖：

```powershell
python -m pip install -r requirements.txt
python -m pip install PyYAML
```

## Environment Variables

推荐只通过环境变量提供 key，不要把密钥写入仓库。

PowerShell 示例：

```powershell
$env:DEEPSEEK_API_KEY = "your-key"
$env:OPENAI_API_KEY = "your-key"
$env:GEMINI_API_KEY = "your-key"
$env:ZHIPUAI_API_KEY = "your-key"
$env:WECHAT_PUBLIC_API_KEY = "your-key"
$env:OCR_SPACE_API_KEY = "your-key"
```

项目中 LLM 的默认环境变量名定义在 [config.py](/E:/PHYS33/StudentsUnion/Wanyou/config.py)：

- `DEEPSEEK_API_KEY_ENV`
- `OPENAI_API_KEY_ENV`
- `GEMINI_API_KEY_ENV`
- `ZHIPUAI_API_KEY_ENV`
- `WECHAT_IMAGE_LLM_API_KEY_ENV`

## Main Pipeline

总控入口在 [main.py](/E:/PHYS33/StudentsUnion/Wanyou/main.py)。

主函数：

- `main()`
- `run_pipeline(...)`

`run_pipeline(...)` 支持这些关键参数：

- `public_only`
- `include_wechat`
- `synthesize`
- `export_docx`
- `export_html`
- `export_agent_payload`

这意味着你可以把完整流程拆成 smoke test、公开站点测试、带登录全量运行等多种模式。

## Skills

项目内置了四个可独立调用、便于 debug 的 skills，全部位于 [skills](/E:/PHYS33/StudentsUnion/Wanyou/skills)。

### 1. Campus Crawl

- Skill: [skills/wanyou-campus-crawl/SKILL.md](/E:/PHYS33/StudentsUnion/Wanyou/skills/wanyou-campus-crawl/SKILL.md)
- 作用：抓取校园网页，区分公开源和登录源，优先定位抓取失败原因

关注文件：

- [wanyou/crawlers_info.py](/E:/PHYS33/StudentsUnion/Wanyou/wanyou/crawlers_info.py)
- [wanyou/crawlers_myhome.py](/E:/PHYS33/StudentsUnion/Wanyou/wanyou/crawlers_myhome.py)
- [wanyou/crawlers_lib.py](/E:/PHYS33/StudentsUnion/Wanyou/wanyou/crawlers_lib.py)
- [wanyou/crawlers_hall.py](/E:/PHYS33/StudentsUnion/Wanyou/wanyou/crawlers_hall.py)
- [wanyou/crawlers_physics.py](/E:/PHYS33/StudentsUnion/Wanyou/wanyou/crawlers_physics.py)

### 2. LLM Filter

- Skill: [skills/wanyou-llm-filter/SKILL.md](/E:/PHYS33/StudentsUnion/Wanyou/skills/wanyou-llm-filter/SKILL.md)
- 作用：处理关键词规则、LLM keep/drop、摘要和过渡语

关注文件：

- [wanyou/decider.py](/E:/PHYS33/StudentsUnion/Wanyou/wanyou/decider.py)
- [wanyou/synthesizer.py](/E:/PHYS33/StudentsUnion/Wanyou/wanyou/synthesizer.py)
- [wanyou/utils_llm.py](/E:/PHYS33/StudentsUnion/Wanyou/wanyou/utils_llm.py)

### 3. Richtext Export

- Skill: [skills/wanyou-richtext-export/SKILL.md](/E:/PHYS33/StudentsUnion/Wanyou/skills/wanyou-richtext-export/SKILL.md)
- 作用：把 Markdown 导出成 H5 HTML、浏览器 Agent payload，必要时导出 DOCX

关注文件：

- [generators/h5_generator.py](/E:/PHYS33/StudentsUnion/Wanyou/generators/h5_generator.py)
- [generators/browser_agent.py](/E:/PHYS33/StudentsUnion/Wanyou/generators/browser_agent.py)

### 4. Full Run

- Skill: [skills/wanyou-full-run/SKILL.md](/E:/PHYS33/StudentsUnion/Wanyou/skills/wanyou-full-run/SKILL.md)
- 脚本： [skills/wanyou-full-run/scripts/run_wanyou_full_run.py](/E:/PHYS33/StudentsUnion/Wanyou/skills/wanyou-full-run/scripts/run_wanyou_full_run.py)
- 作用：一次运行整条流水线并返回产物路径

## AGENTS.md

项目总控与模块关系见 [AGENTS.md](/E:/PHYS33/StudentsUnion/Wanyou/AGENTS.md)。

这里定义了：

- 各模块职责
- 调试顺序
- 一键运行命令
- 典型超时/网络问题来源

推荐调试顺序：

1. 先测 `Campus Crawl`
2. 再看 `LLM Filter`
3. 最后看 `Richtext Export`
4. 一切正常后再跑 `Full Run`

## One-Run Commands

公开站点 smoke run：

```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --public-only --skip-docx
```

带登录源的全量运行：

```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login
```

如果只想验证富文本链路：

```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --public-only --skip-wechat --skip-docx
```

## Campus Site Connectivity

下面是当前项目涉及的校园网页及其联网方式。

### Login-Required Sources

这两类站点依赖 WebVPN / 校园身份认证：

- 教务信息 `URL_INFO`
- 家园网 `URL_MYHOME`

联网方式：

- 先保证可以访问清华 WebVPN
- 运行时输入校园账号密码
- 由 Selenium 在浏览器内完成登录后抓取

适合命令：

```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login
```

### Public Sources

以下站点默认按公开 HTTPS 访问：

- 图书馆通知 `URL_LIB_NOTICE`
- 图书馆活动 `URL_LIB_EVENT`
- 新清华学堂 `URL_HALL_PAGES`
- 物理系学术活动 `PHYSICS_REPORT_LIST_PAGES`

联网方式：

- 直接公网 HTTPS
- 不需要校园账号
- 优先用于 smoke test 和网络排障

适合命令：

```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --public-only --skip-docx
```

### WeChat Public History

公众号历史抓取不直接连微信，而是通过 `down.mptext.top` API：

- 账号搜索 `/account`
- 历史文章 `/article`
- 正文下载 `/download`

联网方式：

- 访问第三方 API
- 可选 `WECHAT_PUBLIC_API_KEY`
- 可选 OCR.Space

独立运行：

```powershell
python wechat_public.py
```

## Richtext Outputs

默认输出目录在 `output/<timestamp>/`。

可能生成这些文件：

- `wanyou_<timestamp>_raw.md`
- `wanyou_<timestamp>.md`
- `wanyou_<timestamp>.html`
- `wanyou_<timestamp>_agent.json`
- `wanyou_<timestamp>.docx`

说明：

- HTML 是默认富文本验证目标
- Agent JSON 是后续秀米/浏览器自动填充的输入
- DOCX 依赖本地 `pandoc`

## LLM Routing

LLM 路由集中在 [wanyou/utils_llm.py](/E:/PHYS33/StudentsUnion/Wanyou/wanyou/utils_llm.py)。

当前支持：

- `deepseek`
- `openai`
- `chatgpt`
- `gemini`
- `zhipuai`

切换方式在 [config.py](/E:/PHYS33/StudentsUnion/Wanyou/config.py)：

```python
LLM_ENABLED = True
LLM_PROVIDER = "deepseek"
LLM_MODEL = "deepseek-chat"
```

微信图片分类也支持单独 provider：

- `WECHAT_IMAGE_LLM_PROVIDER`
- `WECHAT_IMAGE_LLM_MODEL`
- `WECHAT_IMAGE_LLM_API_KEY_ENV`
- `WECHAT_IMAGE_LLM_BASE_URL`

## Known Network Notes

如果外部网络不稳定，当前代码会尽量做到：

- 单个站点失败不阻断整条流水线
- 最终仍然导出 Markdown / H5 / Agent payload
- 在 fallback 文本中记录抓取失败原因

常见现象：

- `WinError 10013`
- `ERR_CONNECTION_CLOSED`
- `ERR_CONNECTION_RESET`
- renderer timeout

这类问题优先视为网络环境、代理、防火墙、站点连接策略或校园访问条件问题，而不是内容解析逻辑问题。

## Validation

当前本地已完成的验证包括：

- Python 编译检查
- skill 结构检查
- DeepSeek API 调用验证
- H5 模板导出验证
- browser-agent payload 导出验证
- `public-only` 一键运行验证

如果外站当天不可达，系统仍会输出可编辑的富文本模板结果，而不是直接中断。
