---
name: wanyou-full-run
description: 端到端跑完整条万有流水线，产出 raw Markdown、ranked raw、最终 Markdown、带「一键复制到公众号」按钮的 H5 HTML、browser-agent payload，以及秀米草稿（秀米只能靠 --preserve-styles 保样式）。需要一条命令生成或调试完整万有流程时使用，尤其适合 public-only 冒烟运行和带登录来源的完整运行。
---

# 万有完整运行

## 流程

1. 调试单个来源时，先用模块级运行（`scripts/run_wanyou_module.py`）。
2. 冒烟测试和外部调试用 `--public-only`。
3. 有校园网凭据时用 `--with-login`。
4. 当前完整链路：来源页面与接口 → raw Markdown → LLM 打分排序的 ranked raw → 选题清洗后的最终 Markdown/HTML → **公众号用 H5 的一键复制按钮**；**秀米必须再跑一遍 `--preserve-styles`**（粘贴到秀米会掉样式）。
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
- 公众号抓取走微信读书：撞上 `-2041`（人机校验）时**程序自己会等**——它把调试 Chrome
  顶到前台、打印「请到打开的 Chrome 窗口里手动完成，完成后我会自动继续」，然后每 5 秒重试、
  每 60 秒报进度，最长 `WEREAD_RISK_WAIT_SECONDS`（默认 600 秒），通过后自动继续。
  你要做的只是把提示转给用户，**别重跑、别重启那个 Chrome**（校验信任只在那个窗口里，
  重启要重新过验证，反复重试还会加重风控）。`-2010`（登录失效）才需要重新扫码后重跑。
  `-2003` 不是风控，是**请求参数格式错误**（多为 `bookId`/URL 传错），先打印真实请求核对，
  排查方向完全不同。
- 留好脚本输出的产物路径，方便后续排查。
