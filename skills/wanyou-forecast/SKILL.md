---
name: wanyou-forecast
description: Generate complete 万有预报 using multi-agent parallel execution. Each source module runs in parallel via sub-agents, then results are integrated, synthesized, exported to H5 HTML, and saved to 秀米草稿. Use when you need a full forecast from scratch with maximum parallelism.
---

# Wanyou Forecast (Multi-Agent)

## Overview

Generate a complete 万有预报 by running source modules in parallel via Claude Code's Agent tool, then integrating, synthesizing, and publishing to 秀米.

Pipeline: parallel module crawls → combine raw → LLM synthesis (with ranked raw) → H5 export → 秀米 draft

## Workflow

### Phase 1 — Parallel Module Execution

Launch all independent module agents **simultaneously** in a single message using the Agent tool. Each agent runs one module and produces raw Markdown.

**Agent A — 公众号 (WeChat):**
```
cd E:/StudentsUnion/Wanyou && python scripts/run_wanyou_module.py wechat --raw-only --md-only
```

**Agent B — 物理系学术报告 (Physics):**
```
cd E:/StudentsUnion/Wanyou && python scripts/run_wanyou_module.py physics --raw-only --md-only
```

**Agent C — 图书馆 (Library):**
```
cd E:/StudentsUnion/Wanyou && python scripts/run_wanyou_module.py lib --raw-only --md-only
```

**Agent D — 新清华学堂 (Hall):**
```
cd E:/StudentsUnion/Wanyou && python scripts/run_wanyou_module.py hall --raw-only --md-only
```

**Agent E — 教务通知 + 家园网 (Login-required):**
```
cd E:/StudentsUnion/Wanyou && python scripts/run_wanyou_module.py login --raw-only --md-only
```

CRITICAL: Launch all 5 agents in ONE message using parallel Agent tool calls. Each agent's `description` should name the module (e.g., "wechat crawl", "physics crawl"). Use subagent_type "general-purpose".

Agents A-D are fully independent. Agent E requires unified auth (will open a browser for login if needed). If Agent E prompts for credentials, tell the user to complete the browser login.

Wait for ALL agents to complete before proceeding to Phase 2.

### Phase 2 — Collect Outputs

After all agents finish, find each module's output directory. The script prints the `run_dir` path. Look for lines like:
- `raw_markdown_path: E:/StudentsUnion/Wanyou/output/module_wechat_YYYYMMDD_HHMM/wanyou_wechat_raw.md`

If an agent's output path is unclear, find it with:
```
ls -td E:/StudentsUnion/Wanyou/output/module_<name>_*/ | head -1
```

Collect all `*_raw.md` file paths.

### Phase 3 — Combine Raw Markdown

Create a combined raw markdown file by concatenating all module raw outputs. The raw files use `# Section` headers — keep the structure intact. Create the combined file in a new integration directory:

```bash
INTEGRATION_DIR=E:/StudentsUnion/Wanyou/output/integration_$(date +%Y%m%d_%H%M)
mkdir -p "$INTEGRATION_DIR"
```

Concatenate all raw files into `$INTEGRATION_DIR/wanyou_combined_raw.md`. Each module's raw file starts with `# <SectionName>`, so concatenation is straightforward.

### Phase 4 — LLM Synthesis & Ranking

First, generate ranked raw by having the LLM score and rank all items — this is a valuable inspection artifact for debugging selection quality:

```bash
cd E:/StudentsUnion/Wanyou && python -c "
import sys; sys.path.insert(0, '.')
from wanyou.raw_ranker import build_ranked_raw_markdown
raw_path = '$INTEGRATION_DIR/wanyou_combined_raw.md'
out_path = '$INTEGRATION_DIR/wanyou_combined_ranked_raw.md'
ranked = build_ranked_raw_markdown(open(raw_path, encoding='utf-8').read(), current_markdown_path=raw_path, clean_with_llm=False)
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(ranked)
print(f'Ranked raw: {out_path}')
"
```

> **保留 ranked_raw 用于 debug：** 这份文件记录了 LLM 对每条原始信息的打分和排序结果。用户可以对比 raw → ranked_raw → final 来理解哪些条目被选中、哪些被过滤，便于后续调整 tendency 或 prompt。

Then run the full synthesis pass. The synthesizer handles temporal filtering, per-section item selection (max 4 per section, 5 for WeChat, physics limited by event date), summaries, transitions, and theme decoration:

```bash
cd E:/StudentsUnion/Wanyou && python skills/wanyou-llm-filter/scripts/run_wanyou_llm_filter.py "$INTEGRATION_DIR/wanyou_combined_raw.md" --output "$INTEGRATION_DIR/wanyou_combined.md"
```

Note: Past physics reports (event date > 12 hours ago) are automatically excluded. This is expected — 万有预报 is forward-looking.

### Phase 5 — Export H5 HTML

Export the final markdown to themed H5 HTML:

```bash
cd E:/StudentsUnion/Wanyou && python skills/wanyou-richtext-export/scripts/run_wanyou_richtext_export.py "$INTEGRATION_DIR/wanyou_combined.md" --skip-agent-payload --title "万有预报"
```

Note the output HTML path printed as `html_path: ...`.

### Phase 6 — Save to 秀米草稿

Push the final HTML + Markdown to 秀米:

```bash
cd E:/StudentsUnion/Wanyou && python scripts/publish_xiumi_draft.py "$INTEGRATION_DIR/wanyou_combined.html" --markdown "$INTEGRATION_DIR/wanyou_combined.md" --title "万有预报"
```

This will:
- Open 秀米 workspace and confirm login
- Create a new draft, fill text and upload images
- Save the draft and output the `xiumi_draft_url`

After save completes, the browser stays open for manual editing. Tell the user to press Enter in the terminal when done.

## 秀米上传的坑(2026-08 排查总结)

这些是经真实草稿验证过的 Xiumi 行为。改 `scripts/publish_xiumi_draft.py` 的编辑器写入逻辑前必读。

### 1. 直接注入 innerHTML 会保存但永不渲染 —— 草稿打开是空的

- Xiumi 编辑器是 Angular 应用。渲染层是 `comps.items`;通过 `innerHTML=` 或 `scope.cell.text=` 注入的内容落在 `_qiBlock.items`(冻结层,能保存但永不渲染)。
- 症状:保存显示成功、草稿 URL 存在,但打开正文一片空白。
- 修复:**受信粘贴**。`navigator.clipboard.write([new ClipboardItem({'text/html': blob, 'text/plain': blob})])` → 聚焦 `[contenteditable]` → CDP `Input.dispatchKeyEvent` Ctrl+V(`modifiers:2, key:"v", code:"KeyV", windowsVirtualKeyCode:86`)。这会让 Xiumi 自己的 paste handler 构建渲染层组件。
- 验证:打开草稿后用 `/data/editing` 接口(或 `output/parse_verify.py`)检查,渲染内容在 `comps.items`,不是 `_qiBlock`。

### 2. CDP 前置条件

```python
browser.execute_cdp_cmd("Browser.grantPermissions", {
  "permissions": ["clipboardReadWrite", "clipboardSanitizedWrite"],
  "origin": "https://xiumi.us"})
browser.execute_cdp_cmd("Emulation.setFocusEmulationEnabled", {"enabled": True})
```

### 3. 持久化 profile 的恢复对话框会挡住编辑器

打开编辑页可能弹「检测到...上次没有保存到服务器，是否恢复?」,挡住编辑器。必须点 `取消`/`确定` 才能继续。脚本已用 `_dismiss_xiumi_recover_dialog` 自动处理。

### 4. 「清空再粘贴」幂等,但相同内容二次粘贴会清空草稿

- 清空 = Ctrl+A(`modifiers:2,key:"a",code:"KeyA",vk:65`) + Delete(`vk:46`),然后重新粘贴,最终只保留最后一次内容(已验证)。
- 血泪教训:当 HTML 无图片时 `final_html == text_first_html`,第二次「清空再粘贴」会把已渲染内容清空 → 空草稿。因此 `_fill_xiumi_body_then_images` 里有 `if final_html != text_first_html:` 守卫,无图片时跳过二次粘贴。

### 5. paste handler 会剥掉所有行内样式

- 只保留 `text-align:justify`;`<h1>/<h2>/<h3>` 被映射为语义字号 180%/140%/120%;相邻段落合并成**一个**文本组件。
- 结论:想靠粘贴保留颜色/背景/边框是行不通的,要保住完整设计样式必须用下面第 8 点的 `--preserve-styles` 模型构建模式。标题层级可靠第 6 点保住。

### 6. 标题层级要靠 `_promote_headings_for_xiumi` 保住

- 大字号 `<p>` 的 `font-size` 会被剥掉。改写前先把大字号段落提升为语义标签:size≥34→`<h1>`,≥20→`<h2>`,≥17+bold→`<h3>`(保留 `text-align`,h1/h2 加 `letter-spacing:2px`)。
- 命令加 `--no-base-format` 才会走标题提升(默认会做 14px/18px 基础格式化,会压扁自定义大字号)。

### 7. PowerShell 环境变量不继承

PowerShell 工具不继承 bash 的 env;每条命令都要设 `$env:WANYOU_SELENIUM_BROWSER='chrome'`。Bash 沙箱会挡 win32 API,win32 操作用 PowerShell。

### 8. 要保住完整设计样式 → 用 `--preserve-styles` 直接构建模型 comps

粘贴路径保不住颜色/背景/边框,但**直接往模型写样式可以,渲染、保存、导出预览全部原样保留**(已验证草稿 717852476、717852825,2026 迎新推送草稿亦如此)。

```powershell
python scripts/publish_xiumi_draft.py "xxx.html" --title "标题" --preserve-styles
```

原理与步骤:
- 解析设计稿里每个**顶层 `<section>`** 为一个块:section 的行内 CSS 转 camelCase 写进 `comps.items[].txt1.style`;内层 HTML(段落/行内 span 的行内样式)写进 `txt1.text`。
- 嵌套 `<section>`/`<div>` 转成 `<p>`(保留其 style,浏览器会自动闭合嵌套 `<p>`),清掉空 `<p></p>`。
- 流程:seed 粘贴 → `scope.$apply` 里替换 `layer.comps.items` → 标记 dirty → 保存。
- 访问模型:`window.angular.element(contenteditable).scope()._$.pages[0].layers[0].comps.items`。
- comp schema:`{_comp:{constraint:{opMenu:{"text-merged":true},pose:{resize:"h"}},pose:{position:"static",width:null,height:null},style:{},tplId:"paper-cp:header/1-txt-normal",_$uuid:"comp-xxx"}, txt1:{type:"text",text:"<p style=...>...</p>",style:{camelCase CSS}}}`
- 圆形数字徽章、橙色胶囊标题、渐变背景、虚线占位框这些行内样式都能保留。
- 仅限纯文本内容;检测到图片时自动退回基础粘贴流程。

## Quick Mode (2-Agent)

For a faster but less granular run, use only 2 agents in Phase 1:

**Agent 1 — Public sources:**
```
cd E:/StudentsUnion/Wanyou && python scripts/run_wanyou_module.py public --raw-only --md-only
```

**Agent 2 — Login sources:**
```
cd E:/StudentsUnion/Wanyou && python scripts/run_wanyou_module.py login --raw-only --md-only
```

Then proceed with Phases 2-6 normally.

## Skipping Modules

To skip a module, simply omit its agent in Phase 1. Common scenarios:
- Skip Agent E (login) if campus credentials are unavailable → use `public` mode
- Skip Agent A (wechat) if `WECHAT_PUBLIC_API_KEY` is expired
- Run only Agent B (physics) for a quick physics-only forecast

## Environment

All agents run in the project root `E:/StudentsUnion/Wanyou`. The `.env` file in the project root is auto-loaded by the scripts.

Required env vars (checked by scripts):
- `DEEPSEEK_API_KEY` — LLM API key
- `WANYOU_USERNAME` / `WANYOU_PASSWORD` — for login modules
- `WECHAT_PUBLIC_API_KEY` — for wechat module

## Debug Notes

- If an agent fails, check its output for errors. Other agents' results are still usable.
- Phase 3 concatenation preserves `# Section` headers from each module — do NOT strip or modify them.
- Phase 4 ranked_raw is an inspection artifact — compare raw → ranked_raw → final to understand LLM selection.
- If 秀米 save fails, check `output/xiumi_debug/*.jsonl` for diagnostics.
- Use `--xiumi-dry-run` in Phase 6 to test without actually saving a draft.
- The physics section is skipped during LLM text cleaning (原始摘要保留).
