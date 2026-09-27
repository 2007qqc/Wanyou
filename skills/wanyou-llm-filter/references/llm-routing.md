# LLM 路由备注

- provider 路由集中在 `wanyou/utils_llm.py`。
- 默认的保留/剔除行为在 `wanyou/decider.py`。
- `INTERACTIVE_REVIEW` 为 `False` 时，未决条目回落到 `DEFAULT_COPY_WHEN_UNDECIDED`。
- 摘要与栏目过渡语在 `wanyou/synthesizer.py` 生成。

## 输出上限与思考强度

两个开关都在 `config.py`，请求体里由 `wanyou/utils_llm.py` 统一拼装——各调用点不再自己传 `max_tokens`：

- `LLM_MAX_TOKENS`：默认 `0`，表示不下发 `max_tokens`，用服务端默认额度（非思考 8K、思考 64K、`reasoning_effort=max` 时 128K，上限 384K）。设成正数才会下发。
- `DEEPSEEK_REASONING_EFFORT`：默认 `medium`，只对 `deepseek` 下发。`none` 关闭思考模式，`low`/`high`/`max` 开启并指定强度；`medium` 是官方兼容别名，实际等同 `high`。

注意两点：

- 旧代码在各调用点写死的 5~800 太小，一旦被截断，调用方的 `or fallback` 会**静默降级**（摘要变回原文、选题列表变空），日志上看不出错。嫌输出长要先查 prompt，别急着收紧 `LLM_MAX_TOKENS`。
- 思考模式下 `temperature` 不生效（官方说明：不报错，但也不起作用）。要让它重新起作用，把 `DEEPSEEK_REASONING_EFFORT` 设成 `none`。
