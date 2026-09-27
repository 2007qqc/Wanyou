# LLM 路由备注

- provider 路由集中在 `wanyou/utils_llm.py`。
- 默认的保留/剔除行为在 `wanyou/decider.py`。
- `INTERACTIVE_REVIEW` 为 `False` 时，未决条目回落到 `DEFAULT_COPY_WHEN_UNDECIDED`。
- 摘要与栏目过渡语在 `wanyou/synthesizer.py` 生成。
