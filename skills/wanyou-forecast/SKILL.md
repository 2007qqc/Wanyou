---
name: wanyou-forecast
description: 用多 agent 并行抓取各来源，再整合、LLM 合成、导出 H5、存成秀米草稿，一键产出完整《万有预报》。需要从零生成一期预报、且要求最大并行度时使用。
---

# 万有预报（多 Agent）

## 概览

用 Claude Code 的 Agent 工具并行跑各来源模块，再整合、合成、推送秀米。

流程：并行抓取 → 合并 raw → LLM 打分与合成（含 ranked raw）→ 导出 H5 → 秀米草稿

命令里的 `python` 一率用项目虚拟环境：`E:/StudentsUnion/Wanyou/.venv/Scripts/python.exe`（裸 `python` 在本机是微软商店占位程序，直接退 9009）。

## 流程

### 阶段 1 —— 并行跑模块

在**同一条消息**里用 Agent 工具一次性发出全部 5 个 agent，每个跑一个模块并产出 raw Markdown。`subagent_type` 用 `general-purpose`，`description` 写明模块名（如 "wechat crawl"）。

| Agent | 模块 | 命令 |
|---|---|---|
| A | 公众号 | `python scripts/run_wanyou_module.py wechat --raw-only --md-only` |
| B | 物理系学术报告 | `python scripts/run_wanyou_module.py physics --raw-only --md-only` |
| C | 图书馆 | `python scripts/run_wanyou_module.py lib --raw-only --md-only` |
| D | 新清华学堂 | `python scripts/run_wanyou_module.py hall --raw-only --md-only` |
| E | 教务通知 + 家园网 | `python scripts/run_wanyou_module.py login --raw-only --md-only` |

均在项目根目录 `E:/StudentsUnion/Wanyou` 下执行。A–D 相互独立；A 会起一个专用调试 Chrome 并等微信读书登录/人机校验，E 需要统一身份认证——两者都会开浏览器等登录，把 agent 的提示转给用户，让 TA 在浏览器里完成即可，别自己重试。

**等全部 agent 结束**再进阶段 2。

### 阶段 2 —— 收集产物

每个模块的目录形如 `output/module_<名字>_YYYYMMDD_HHMM/`，脚本会打印 `raw_markdown_path: ...`。拿不到就：

```bash
ls -td E:/StudentsUnion/Wanyou/output/module_<name>_*/ | head -1
```

收集所有 `*_raw.md` 路径。

### 阶段 3 —— 合并 raw

把各模块 raw 按顺序拼接（各自以 `# 栏目名` 开头，直接 cat 即可，**不要**改动标题结构）：

```bash
INTEGRATION_DIR=E:/StudentsUnion/Wanyou/output/integration_$(date +%Y%m%d_%H%M)
mkdir -p "$INTEGRATION_DIR"
cat <各 *_raw.md> > "$INTEGRATION_DIR/wanyou_combined_raw.md"
```

### 阶段 4 —— LLM 打分与合成

先出 ranked raw（**必留**，是调试选题质量的依据：对比 raw → ranked_raw → final 就能看出哪条被选中、哪条被过滤）：

```bash
python -c "
import sys; sys.path.insert(0, '.')
from wanyou.raw_ranker import build_ranked_raw_markdown
raw_path = '$INTEGRATION_DIR/wanyou_combined_raw.md'
out_path = '$INTEGRATION_DIR/wanyou_combined_ranked_raw.md'
ranked = build_ranked_raw_markdown(open(raw_path, encoding='utf-8').read(), current_markdown_path=raw_path, clean_with_llm=False)
open(out_path, 'w', encoding='utf-8').write(ranked)
"
```

再跑合成（含时间过滤、每栏目选条上限 4 条 / 公众号 5 条 / 物理系按活动时间、摘要、栏目过渡语、主题装饰）：

```bash
python skills/wanyou-llm-filter/scripts/run_wanyou_llm_filter.py "$INTEGRATION_DIR/wanyou_combined_raw.md" --output "$INTEGRATION_DIR/wanyou_combined.md"
```

物理系过期的报告（活动时间早于当前 12 小时）会被自动剔除，这是预期行为——万有预报只向前看。

### 阶段 5 —— 导出 H5

```bash
python skills/wanyou-richtext-export/scripts/run_wanyou_richtext_export.py "$INTEGRATION_DIR/wanyou_combined.md" --skip-agent-payload --title "万有预报"
```

记下打印的 `html_path:`。

### 阶段 6 —— 存成秀米草稿

**先跑一遍 Markdown 预处理**，它会做三件推秀米必需的事（见 `scripts/prepare_xiumi_markdown.py` 的模块 docstring）：把内嵌 `data:` 图片落地成本地文件、把相对路径改成绝对路径、把被 Markdown 吃掉下划线的路径（`module_lib_20260927_0752` → `modulelib202609270752`）模糊匹配回真实文件。

```bash
python scripts/prepare_xiumi_markdown.py "$INTEGRATION_DIR/wanyou_combined.md"
```

它会打印「残留 data:image ...（必须为 0）」和「仍找不到：N 张」——**这两个数不为 0 就别往下推**，否则会静默丢图。产出是 `wanyou_combined_xiumi.md`。

再推。**`--markdown` 传预处理后的 `_xiumi.md`，`--preserve-styles` 必带**，它才是让草稿带格式的那一步：

```bash
python scripts/publish_xiumi_draft.py "$INTEGRATION_DIR/wanyou_combined.html" --markdown "$INTEGRATION_DIR/wanyou_combined_xiumi.md" --title "万有预报" --preserve-styles
```

标题里的中文不要走命令行——用脚本文件里的 Python 字面量传，避免编码问题。

推完**先看日志**再下结论（`output/xiumi_debug/*.jsonl`）：

| 日志 | 正常值 |
|---|---|
| `xiumi_style_aware_blocks` | 十几到二十几（整篇只 1 个 = 分块退化，见下方「坑 8」） |
| `xiumi_comps_built` | `ok:true`，`compCount` 与上面一致 |
| `xiumi_render_style_probe` | `modelStyle` 与 `domStyle` 都在几百量级 |
| `xiumi_image_cdn_inline` / `xiumi_image_cdn_failed` | 每张本地图都应有 `_cdn_inline` |

草稿存好后浏览器会保持打开供人工微调，让用户在终端按回车结束。

## 秀米写入的坑

以下都是真实草稿验证过的秀米行为。改 `scripts/publish_xiumi_draft.py` 的写入逻辑前必读。

### 1. 直接注入 innerHTML 会保存但永不渲染——草稿打开是空的

秀米编辑器是 Angular 应用。渲染层是 `comps.items`；用 `innerHTML=` 或 `scope.cell.text=` 注入的内容落进 `_qiBlock.items`（冻结层，能保存但永不渲染）。症状是保存成功、URL 能打开、正文一片空白。

修复方式是**受信粘贴**：`navigator.clipboard.write([new ClipboardItem({'text/html': blob, 'text/plain': blob})])` → 聚焦 `[contenteditable]` → CDP `Input.dispatchKeyEvent` Ctrl+V（`modifiers:2, key:"v", code:"KeyV", windowsVirtualKeyCode:86`），让秀米自己的 paste handler 去构建渲染层组件。用 `/data/editing` 接口（或 `output/parse_verify.py`）验证内容在 `comps.items` 而不是 `_qiBlock`。

### 2. CDP 前置条件

```python
browser.execute_cdp_cmd("Browser.grantPermissions", {
  "permissions": ["clipboardReadWrite", "clipboardSanitizedWrite"],
  "origin": "https://xiumi.us"})
browser.execute_cdp_cmd("Emulation.setFocusEmulationEnabled", {"enabled": True})
```

### 3. 恢复对话框会挡住编辑器

持久化 profile 打开编辑页时可能弹「上次没有保存到服务器，是否恢复？」。脚本已用 `_dismiss_xiumi_recover_dialog` 自动点掉。

### 4. 「清空再粘贴」幂等，但相同内容二次粘贴会清空草稿

清空 = Ctrl+A（`key:"a"`, `vk:65`）+ Delete（`vk:46`）。血泪教训：HTML 无图片时 `final_html == text_first_html`，第二次「清空再粘贴」会把已渲染内容清空成空草稿。因此 `_fill_xiumi_body_then_images` 里有 `if final_html != text_first_html:` 守卫。

### 5. paste handler 会剥掉所有行内样式

只留 `text-align:justify`；`<h1>/<h2>/<h3>` 被映射成语义字号 180%/140%/120%；相邻段落合并成**一个**文本组件。所以想靠粘贴保住颜色/背景/边框是行不通的——要完整设计样式必须走「坑 8」的模型构建模式。标题层级可以靠「坑 6」保住。

### 6. 标题层级靠 `_promote_headings_for_xiumi` 保住

大字号 `<p>` 的 `font-size` 会被剥掉，所以改写前先把大字号段落提升为语义标签：size≥34 → `<h1>`，≥20 → `<h2>`，≥17 且 bold → `<h3>`（保留 `text-align`，h1/h2 加 `letter-spacing:2px`）。命令加 `--no-base-format` 才会走标题提升（默认会做 14px/18px 基础格式化，把自定义大字号压平）。

### 7. PowerShell 环境变量不继承

PowerShell 工具不继承 bash 的 env，每条命令都要单独设 `$env:WANYOU_SELENIUM_BROWSER='chrome'`。Bash 沙箱会挡 win32 API，win32 相关操作用 PowerShell。

### 8. 保住完整设计样式 → `--preserve-styles` 直接构建模型 comps

粘贴路径保不住颜色/背景/边框，但**直接往模型写样式可以，渲染、保存、导出预览全部原样保留**（已验证草稿 717852476、717852825，2026 迎新推送亦如此）。

```powershell
python scripts/publish_xiumi_draft.py "xxx.html" --title "标题" --preserve-styles
```

做法：

- 把源 HTML 里**每个有内容的 `<section>`** 解析成一个块——**不只顶层，要逐层下沉到卡片一级**。该 section 的行内 CSS 转 camelCase 写进 `comps.items[].txt1.style`；内层 HTML（段落、行内 span 的行内样式）写进 `txt1.text`。嵌套 `<section>`/`<div>` 转成 `<p>`（保留其 style），清掉空 `<p></p>`。
- 顶层 `<section>` 通常只是包住整篇的页面外壳，不成块，只把可继承的样式传下去：`background`/`color`/`font-family`/`line-height`/`font-size` 继承；`padding`/`border`/`border-radius` **不继承**（继承了每个子块会再画一个框）。
- 卡片文字「包住」嵌套块（子块前后都有文字）时整张卡不拆——拆开会把一张卡片断成上下两个框，顺序也会乱。
- 流程：seed 粘贴 → 在 `scope.$apply` 里替换 `layer.comps.items` → 标记 dirty → 保存。模型位置：`window.angular.element(contenteditable).scope()._$.pages[0].layers[0].comps.items`。
- comp schema：`{_comp:{constraint:{opMenu:{"text-merged":true},pose:{resize:"h"}},pose:{position:"static",width:null,height:null},style:{},tplId:"paper-cp:header/1-txt-normal",_$uuid:"comp-xxx"}, txt1:{type:"text",text:"<p style=...>...</p>",style:{camelCase CSS}}}`
- 圆形数字徽章、橙色胶囊标题、渐变背景、虚线占位框这些行内样式都能保留。
- 图片走 `_fill_xiumi_body_style_aware_with_images`：先把**本地文件**图片粘贴转成 `img.xiumi.us` 的 CDN 地址（URL 带 `-sz_<字节数>`，可用来校验是否是真图），再内联进文本 comp。**`data:` URL 图片转不出 CDN 地址**，保存后会被秀米剥离，所以必须先把图落地成本地文件。
- **这条粘贴通道有文件大小上限。** 实测 0.4 MB 的图全过、6~7 MB 的新清华学堂海报全挂（`xiumi_image_cdn_failed`，草稿里是断图）。现在超过 `XIUMI_IMAGE_MAX_BYTES`（默认 1 MB）的图会先用 canvas 降到最长边 `XIUMI_IMAGE_MAX_DIMENSION`（默认 1600px）再粘，日志记 `xiumi_image_shrunk`；仍失败则换成 `[配图上传未完成…]` 占位。查日志时 `xiumi_image_cdn_inline` 的条数应当等于本地图总数。
- **「只取顶层 `<section>`」是个已复现的真 bug**：万有正文只有一个顶层 section 包住整篇，于是整篇挤进**一个** comp（日志 `xiumi_style_aware_blocks count=1` → `xiumi_comps_built compCount=1`），卡片的 `background`/`border`/`border-radius` 全部从 comp 级掉进文本内部，渲染出来就是**无格式正文**。能正常显示的已验证草稿（717852476 / 717852825 / 718085184）都是 10–11 个 comp、卡片样式在 comp 级。下沉到卡片级后同一份稿子得到 19 个 comp、19 个都带 comp 级样式，文本内容与原来逐字节一致。
- 排查「草稿没格式」先看 `xiumi_render_style_probe`：它同时记录**模型里**和**真正渲染出来的 DOM 里**的样式数。模型有、渲染层没有 → 渲染层在丢；两边都有却仍无格式 → 问题不在渲染。

## 快速模式（2 Agent）

阶段 1 只发 2 个 agent，快但粒度粗：`public`（公开来源）+ `login`（需登录来源），之后照常走阶段 2–6。

## 跳过模块

阶段 1 不派对应 agent 即可。常见情形：

- 没有校园网凭据 → 跳过 E，改用 `public`
- 公众号撞上 `-2041`（人机校验）→ 跳过 A，或等用户在那个 Chrome 窗口里过完验证再重跑
- 只想快速出一期物理系 → 只留 B

## 环境

所有 agent 都在项目根目录 `E:/StudentsUnion/Wanyou` 跑，`.env` 会被脚本自动加载。

- `DEEPSEEK_API_KEY` —— LLM
- `WANYOU_USERNAME` / `WANYOU_PASSWORD` —— 需登录的模块
- 公众号模块不再需要密钥：走微信读书（`WECHAT_SOURCE="weread"`），只需要一个已登录的调试 Chrome

**公众号来源是微信读书，不是第三方 API。** 旧的 `down.mptext.top` 域名 2026-10-30 到期，已降级为回滚路径（`WECHAT_SOURCE="mptext"` 时仍可用，但那时仍要 `WECHAT_PUBLIC_API_KEY`，且密钥与站点会话绑定、**只有 4 天有效期**）。

现在的路线：脚本自动用 `--remote-debugging-port=9333` + 独立 profile 起一个专用 Chrome，登录态和人机校验信任都留在这个窗口里，**登录失效或弹验证码时 agent 会停下等用户**——把 A 的错误输出原样告诉用户，让 TA 在那个窗口里扫码/过验证即可，过完重跑 A。撞上 `-2041` 就是人机校验没过（过完验证重跑即可，**不是接口下线**），`-2003` 是**请求参数格式错误**（多为 `bookId`/URL 传错，**别误判成限流**），`-2010` 是登录态失效。

注意：脚本自己 `subprocess.Popen` 起 Chrome 有时起不来（端口 25 秒内不响应）。手动起一次更稳，脚本会直接复用已在运行的实例：

```bash
"C:/Program Files/Google/Chrome/Application/chrome.exe" \
  --remote-debugging-port=9333 \
  --user-data-dir=E:/StudentsUnion/Wanyou/output/selenium_cache/weread-debug-profile \
  --no-first-run --no-default-browser-check https://weread.qq.com/
```

另外 `attach()` 首次可能要一两分钟（Selenium Manager 在解析 driver），之后有缓存就快了，别当成卡死。

## 调试

1. 先看抓取：`*_raw.md` 判断来源是否完整。
2. 再看 ranked raw：`*_ranked_raw.md` 判断 LLM 选题质量。
3. 再看合成稿：`*.md` 判断文字与栏目是否正确。
4. 导出：打开 `*.html` 确认富文本渲染。
5. 秀米：加 `--xiumi-dry-run` 可只跑不保存；诊断看 `output/xiumi_debug/*.jsonl`。
6. 某个 agent 挂了不影响其他来源，先看它的输出报错。
7. 物理系栏目在 LLM 文本清洗阶段会被跳过（保留原始摘要）。
