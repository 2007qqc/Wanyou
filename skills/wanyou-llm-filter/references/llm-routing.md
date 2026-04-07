# LLM Routing Notes

- Provider routing is centralized in `wanyou/utils_llm.py`.
- Default keep/drop behavior lives in `wanyou/decider.py`.
- Undecided items now fall back to `DEFAULT_COPY_WHEN_UNDECIDED` when `INTERACTIVE_REVIEW` is `False`.
- Summaries and transitions are generated in `wanyou/synthesizer.py`.
