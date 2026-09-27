---
name: wanyou-richtext-export
description: 把最终万有 Markdown 导出成 H5 HTML 与 browser-agent payload，不重跑爬虫或 LLM 筛选。需要验证排版、主题、富文本产物或 agent payload 生成时使用。
---

# 万有富文本导出

## 用途

在最终 Markdown 已经存在之后使用。它从 Markdown 文件导出 H5 HTML 和可选的 browser-agent payload。

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
- 需要 DOCX 时走完整流水线，并先确认本机 `pandoc` 可用。
- 富文本导出不应改变爬虫或 LLM 筛选行为。
- 秀米推送要保住已验证的内部顺序：先文本、再图片、最后排版。
- 秀米 stdout 只应出现面向用户的进度与最终状态；上传、选择器、异常等诊断细节写进 `output/xiumi_debug/*.jsonl`。
