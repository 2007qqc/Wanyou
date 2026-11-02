---
name: wanyou-richtext-export
description: 把最终万有 Markdown 导出成带「一键复制到公众号」按钮的 H5 HTML（图片自动内嵌）与 browser-agent payload，不重跑爬虫或 LLM 筛选。需要验证排版、主题、富文本产物或 agent payload 生成时使用。
---

# 万有富文本导出

## 用途

在最终 Markdown 已经存在之后使用。它从 Markdown 文件导出 H5 HTML 和可选的 browser-agent payload。

导出的 H5 右下角带「复制到公众号」按钮：复制的是 `generators/wechat_inline.py` 生成的**全内联样式正文**，图片已由 `wanyou/inline_images.py` 压到最长边 900px 并转成 `data:` 内嵌，粘进**公众号后台**后样式和图片都在，**不需要先上传图片**。

（秀米不吃这套：它的粘贴通道会剥掉行内样式，详见 `wanyou-to-xiumi`。）

## 产物契约：单文件自包含

导出的 HTML 是**单文件**：页面本体和复制源里的 `<img>` 都必须只剩内联 `data:`，不含任何本机/相对路径。把 HTML 单独拷到别处（发给自己、扔进共享盘、删掉整个 `output/`）后双击仍能看图——这是硬要求，不是尽力而为。

脚本在导出后自检并打印：

```text
html_images: total=12 inline=12 remote=0 local=0 size=1,060,776 bytes
html_self_contained: yes（HTML 可单独移动，图片全内联）
```

`local` 非零说明还有图片指在本机文件上，脚本以退出码 1 失败，并列出这些 `src`。修法通常是先落地图片路径（Markdown 会把 `module_lib_...` 里的下划线吃掉，变成不存在的 `modulelib...`）：

```bash
python scripts/prepare_xiumi_markdown.py output/final.md
```

再拿预处理后的 `_xiumi.md` 重新导出。确实要保留本地路径时加 `--allow-local-images`，降级为警告（产物不可单独移动）。


## 命令

导出 HTML 与 agent payload：

```bash
python skills/wanyou-richtext-export/scripts/run_wanyou_richtext_export.py output/module_wechat_YYYYMMDD_HHMM/wanyou_wechat.md
```

指定输出路径：

```bash
python skills/wanyou-richtext-export/scripts/run_wanyou_richtext_export.py output/final.md --html output/final.html --agent-payload output/final_agent.json
```

只导出 HTML：

```bash
python skills/wanyou-richtext-export/scripts/run_wanyou_richtext_export.py output/final.md --skip-agent-payload
```

只导出 browser-agent payload：

```bash
python skills/wanyou-richtext-export/scripts/run_wanyou_richtext_export.py output/final.md --skip-html
```

把已有的最终 HTML/Markdown 送成秀米草稿：

```bash
python scripts/publish_xiumi_draft.py output/final.html --markdown output/final.md --title "万有预报"
```

改 `scripts/publish_xiumi_draft.py` 之前，先读 `references/xiumi-workflow.md` 里的秀米浏览器流程。

## 调试规则

- 富文本验证以 HTML 产物为准。
- HTML 必须自包含：`html_images` 的 `local` 必须是 0，否则这个产物不能单独移动（脚本默认以退出码 1 拦住）。
- 图片路径被 Markdown 吃掉下划线（`module_lib_...` → `modulelib...`）是已知坑，改导出逻辑前先跑 `scripts/prepare_xiumi_markdown.py`。
- 需要 DOCX 时走完整流水线，并先确认本机 `pandoc` 可用。
- 富文本导出不应改变爬虫或 LLM 筛选行为。
- 秀米推送要保住已验证的内部顺序：先文本、再图片、最后排版。
- 秀米 stdout 只应出现面向用户的进度与最终状态；上传、选择器、异常等诊断细节写进 `output/xiumi_debug/*.jsonl`。
