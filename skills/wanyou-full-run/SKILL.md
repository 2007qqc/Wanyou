---
name: wanyou-full-run
description: 端到端跑完整条万有流水线，产出 raw Markdown、ranked raw、最终 Markdown、H5 HTML、browser-agent payload，以及可选的秀米草稿。需要一条命令生成或调试完整万有流程时使用，尤其适合 public-only 冒烟运行和带登录来源的完整运行。
---

# 万有完整运行

## 流程

1. 调试单个来源时，先用模块级运行（`scripts/run_wanyou_module.py`）。
2. 冒烟测试和外部调试用 `--public-only`。
3. 有校园网凭据时用 `--with-login`。
4. 当前完整链路：来源页面与接口 → raw Markdown → LLM 打分排序的 ranked raw → 选题清洗后的最终 Markdown/HTML → 可选秀米草稿。
5. 某个来源缺失时，先看 raw Markdown 路径。
6. 改 prompt 或选题逻辑之前，先看 ranked raw。
7. 送秀米之前，先打开 HTML 产物确认富文本渲染。

## 命令

公开来源冒烟运行：

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --public-only --skip-docx
```

带统一认证来源的完整运行：

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --todo-richtext --skip-docx
```

从零一路跑到秀米草稿：

```bash
python scripts/run_wanyou_to_xiumi_draft.py --with-login --skip-docx
```

调试校园爬虫时跳过公众号：

```bash
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login --skip-wechat --skip-docx
```

## 调试规则

- 怀疑整条流水线之前，先用 `scripts/run_wanyou_module.py <模块>` 单独跑。
- ranked raw 只做打分与排序，不做额外的 LLM 文本清洗。
- 富文本调试以 H5 产物为准。
- 公众号抓取走微信读书：撞上 `-2041`（人机校验）或 `-2010`（登录失效）就停下，
  让用户在专用调试 Chrome 里过验证或重新扫码，然后重跑，别自己反复重试（越试越容易被风控）。
  `-2003` 不是风控，是**请求参数格式错误**（多为 `bookId`/URL 传错），先打印真实请求核对，
  排查方向完全不同。
- 留好脚本输出的产物路径，方便后续排查。
