---
name: wanyou-llm-filter
description: 对 raw Markdown 施加万有的 LLM 保留/剔除决策、条目排序、摘要、栏目过渡语与主题装饰。需要在不重跑爬虫的前提下复测筛选 prompt 或摘要质量时使用。
---

# 万有 LLM 筛选

## 用途

在爬虫模块产出 raw Markdown 之后使用。它读取 raw Markdown，施加 LLM 筛选/排序与摘要，保留必要的来源细节，写出最终 Markdown。

当前筛选策略：

- 只保留万有运行前一周内发布的信息。
- 只保留与清华物理系本科生直接相关的信息。
- 重点关注时间戳、发布方、目标受众与正文。
- 栏目超载时，每栏目最多保留 4 条。
- 公众号由爬虫模块按发布时间取最新 5 篇。
- 避免叠加多轮 LLM 清洗。ranked raw 不应被 LLM 清洗；选题与格式清理的正常位置是最终 Markdown。
- 不要随意截断保留条目。若最终条目丢失了必要细节，先查 `LLM_MAX_TOKENS` 与 prompt，而不是缩短来源正文。

## 命令

```bash
python skills/wanyou-llm-filter/scripts/run_wanyou_llm_filter.py output/module_wechat_YYYYMMDD_HHMM/wanyou_wechat_raw.md
```

指定输出路径：

```bash
python skills/wanyou-llm-filter/scripts/run_wanyou_llm_filter.py input_raw.md --output output/final.md
```

跳过主题装饰：

```bash
python skills/wanyou-llm-filter/scripts/run_wanyou_llm_filter.py input_raw.md --no-theme
```

## 调试规则

- 某条目被意外保留时，先查 `wanyou/decider.py` 与 `wanyou/synthesizer.py` 的 prompt。
- 完全没有 LLM 调用时，检查 `LLM_ENABLED`、provider 设置与 API key 环境变量。
- 输出过长时，先查栏目选题与最终摘要 prompt，再考虑加硬截断。
