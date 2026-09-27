---
name: wanyou-to-xiumi
description: 一条命令从零跑到秀米草稿——跑完整个万有流水线并直接推送到秀米；也支持把已有的 .html/.md 产物单独发到秀米。需要产出成品秀米草稿时使用。
---

# 万有 → 秀米草稿

## 用途

一条命令从零到已保存的秀米草稿：校园爬虫（可选统一认证）+ LLM 选题排序 + 富文本生成 + 秀米编辑器自动化（正文、图片、保存）。也支持不重跑爬虫、直接把已有产物发到秀米。

```text
网页和公众号来源 → raw Markdown → LLM 打分 ranked raw → 清洗选优合成 Markdown/HTML → 秀米草稿
```

秀米内部的顺序：写正文（图片留占位）→ 上传图片到「我的图库(无水印)」→ 回填图片地址 → 应用最终版式 → 保存。

命令里的 `python` 一律用项目虚拟环境：`E:/StudentsUnion/Wanyou/.venv/Scripts/python.exe`（裸 `python` 在本机是微软商店占位程序，直接退 9009）。

## 命令

### 一条命令：全流水线 + 秀米草稿

```powershell
python scripts/run_wanyou_to_xiumi_draft.py --with-login --skip-docx
```

常用变体：

| 场景 | 追加参数 |
|---|---|
| 只用公开来源（不登录） | `--public-only` |
| 自定义标题 | `--title "万有预报"` |
| 试跑：填充编辑器但不点保存 | `--xiumi-dry-run` |
| 公众号密钥失效时跳过公众号 | `--skip-wechat` |
| 自定义封面 | `--xiumi-cover badge.png` |
| 跨次复用浏览器 profile | `--xiumi-profile-dir output/selenium_cache/my-xiumi-profile` |

### 单独发布已有产物

流水线已跑完、手上有最终 `.html` + `.md` 时：

```powershell
python scripts/publish_xiumi_draft.py output/xxx/wanyou_xxx.html --markdown output/xxx/wanyou_xxx.md --title "万有预报" --preserve-styles
```

**`--preserve-styles` 是带格式的前提。** 不带它就走受信粘贴路径，秀米的 paste handler 会把行内 CSS 全部剥掉——草稿照样保存成功、URL 也能打开，但正文是无格式纯文本。前置条件：markdown 里不能有内嵌 `data:` URL 图片（先落地成本地文件），样式保留路径只把**本地文件**图片转成秀米 CDN。

只想试跑不保存，加 `--dry-run`。

## 图片控制

| `XIUMI_IMAGE_MODE` | 行为 |
|---|---|
| `upload`（默认） | 本地图上传到秀米图库再回填地址，质量最好 |
| `inline` | 本地图转 base64 内联，HTML 变大但不走上传 |
| `auto` | 先试 inline，超过 `XIUMI_MAX_INLINE_IMAGE_HTML_CHARS` 就退化成 omit |
| `omit` | 删掉所有图只留占位，最快但草稿无图 |

在 `.env` 里设置：

```ini
XIUMI_IMAGE_MODE=upload
XIUMI_MAX_INLINE_IMAGE_HTML_CHARS=900000
```

## 秀米写入的坑（2026-08，真实草稿验证过）

改 `scripts/publish_xiumi_draft.py` 的写入逻辑前必读。

### 直接注入 innerHTML 会保存但永不渲染 → 空草稿

编辑器是 Angular 应用。渲染层是 `comps.items`；用 `innerHTML=` 或 `scope.cell.text=` 注入的内容落进 `_qiBlock.items`（冻结层，能保存但永不渲染）。症状是保存成功、URL 能打开、正文一片空白。

修复方式是**受信粘贴**：`navigator.clipboard.write([new ClipboardItem({'text/html': blob, 'text/plain': blob})])` → 聚焦 `[contenteditable]` → CDP `Input.dispatchKeyEvent` Ctrl+V（`modifiers:2, key:"v", code:"KeyV", windowsVirtualKeyCode:86`），让秀米自己的 paste handler 去构建渲染层组件。用 `/data/editing` 接口（或 `output/parse_verify.py`）验证内容在 `comps.items` 而不是 `_qiBlock`。

### CDP 前置条件

```python
browser.execute_cdp_cmd("Browser.grantPermissions", {
  "permissions": ["clipboardReadWrite", "clipboardSanitizedWrite"],
  "origin": "https://xiumi.us"})
browser.execute_cdp_cmd("Emulation.setFocusEmulationEnabled", {"enabled": True})
```

### 持久化 profile 的恢复对话框会挡住编辑器

可能弹「上次没有保存到服务器，是否恢复？」。脚本已用 `_dismiss_xiumi_recover_dialog` 自动点掉。

### 「清空再粘贴」幂等，但相同内容二次粘贴会清空草稿

清空 = Ctrl+A + Delete，然后重新粘贴，只保留最后一次内容。血泪教训：HTML 无图片时 `final_html == text_first_html`，第二次「清空再粘贴」会把已渲染内容清空 → 空草稿。`_fill_xiumi_body_then_images` 用 `if final_html != text_first_html:` 守卫。

### paste handler 会剥掉所有行内样式

只留 `text-align:justify`；`<h1>/<h2>/<h3>` 映射成语义字号 180%/140%/120%；相邻块合并成**一个**文本组件。粘贴保不住颜色/背景/边框，要完整设计样式得走下面的 `--preserve-styles`。

### 用 `--preserve-styles` 保住完整设计样式（模型构建模式）

粘贴会剥样式，但**直接往模型写样式能保住**——渲染、保存、导出预览都会原样保留颜色/背景/边框/字体/渐变/圆形徽章（已验证草稿 717852476、717852825）。

```powershell
python scripts/publish_xiumi_draft.py "xxx.html" --title "标题" --preserve-styles
```

- 把源 HTML 里**每个有内容的 `<section>`** 解析成一个块（**不只顶层，要下沉到卡片级**）：section 的行内 CSS 转 camelCase 写进 `comps.items[].txt1.style`；内层 HTML（段落/行内 span 及其行内样式）写进 `txt1.text`。嵌套 `<section>`/`<div>` 转成 `<p>`（保留 style，浏览器会自动闭合嵌套 `<p>`），清掉空 `<p></p>`。
- **「只取顶层」是已复现的真 bug。** 万有正文只有一个顶层 `<section>` 包住整篇，于是整篇挤进**一个** comp（`xiumi_style_aware_blocks count=1` → `compCount=1`），每张卡片的 `background`/`border`/`border-radius` 从 comp 级掉进文本内部，草稿渲染成**无格式正文**。已知能正常渲染的草稿（717852476 / 717852825 / 718085184）都是 10–11 个 comp、卡片样式在 comp 级。修复后同一份稿子得到 19 个 comp、19 个都带 comp 级样式，文本逐字节一致。
- 顶层 `<section>` 通常只是页面外壳，自己不成块，只把可继承的样式传下去：`background`/`color`/`font-family`/`line-height`/`font-size` 继承；`padding`/`border`/`border-radius` **不继承**，否则每个子块都会再画一个框。
- 卡片文字「包住」嵌套块（子块前后都有文字）时整张卡不拆——拆开会把一张卡断成上下两个框，顺序也会乱。
- 流程：seed 粘贴 → 在 `scope.$apply` 里替换 `layer.comps.items` → 标记 dirty → 保存。模型位置：`window.angular.element(contenteditable).scope()._$.pages[0].layers[0].comps.items`。
- comp schema：`{_comp:{constraint:{opMenu:{"text-merged":true},pose:{resize:"h"}},pose:{position:"static",width:null,height:null},style:{},tplId:"paper-cp:header/1-txt-normal",_$uuid:"comp-xxx"}, txt1:{type:"text",text:"<p style=...>...</p>",style:{camelCase CSS}}}`
- 图片：本地文件图先用粘贴转成 `img.xiumi.us` 的 CDN 地址（URL 带 `-sz_<字节数>`）再内联进文本 comp。**`data:` URL 图片转不出 CDN 地址**，保存后会被秀米静默剥离。
- 草稿看着没格式时先看 `output/xiumi_debug/*.jsonl` 里的 `xiumi_render_style_probe`：它同时记录**模型里**和**真正渲染出来的 DOM 里**的样式数。模型有、渲染层没有 → 渲染层在丢；两边都有 → 问题在别处。

### 标题层级靠 `_promote_headings_for_xiumi` 保住

大字号 `<p>` 的行内 `font-size` 会被剥掉，先提升为语义标签：size≥34 → `<h1>`，≥20 → `<h2>`，≥17 且 bold → `<h3>`（保留 `text-align`，h1/h2 加 `letter-spacing:2px`）。加 `--no-base-format` 才会走标题提升（默认基础格式化会归一成 14px/18px，压平自定义大字号）。

### PowerShell 环境变量不继承

PowerShell 工具不继承 bash 的 env，每条命令都要单独设 `$env:WANYOU_SELENIUM_BROWSER='chrome'`。Bash 沙箱会挡 win32 API，win32 操作用 PowerShell。

## 调试

诊断入口一律是 `output/xiumi_debug/*.jsonl`，改 `scripts/publish_xiumi_draft.py` 前先看它。

- 秀米之前就挂了：看输出目录里的中间产物 `*_raw.md`、`*_ranked_raw.md`、`*_todo_selected_raw.md`、`*.md`、`*.html`。
- 登录失败或检测不到登录：看 jsonl 里的登录诊断；出错时浏览器会保持打开，直接看窗口。
- 全部图片连续失败达到 `XIUMI_IMAGE_UPLOAD_MAX_FAILURES`：脚本中止上传、留下占位。看 jsonl 里的上传探针结果。
- 个别图片失败：跳过并替换成 `[配图上传未完成]` 占位，不阻塞整篇。
- 保存状态「不确定」：草稿可能已保存，看浏览器里的编辑器 URL（保存后浏览器保持打开供人工确认）。
- 页面改版（改版式、改 CSS 选择器）会让内联 JS 启发式失效：看 jsonl 里的 `xiumi_create_failed`、`xiumi_login_not_settled`、`file_input_missing`。
- 进了编辑器但正文没写进去：`contenteditable` / Angular scope 的探测需要更新，看 `xiumi_body_text_model_applied`。
- 用 `--xiumi-dry-run` 试跑，避免在秀米里留下废草稿。
- 用 `--skip-wechat` 绕开公众号抓取失败。公众号走微信读书，卡住通常是 `-2041`（人机校验没过）或 `-2003`（限流），让用户在那个专用调试 Chrome 里过验证，或隔几小时再跑。
- 浏览器 profile 默认在关闭后清理；要保留登录态就显式传 `--xiumi-profile-dir`。
