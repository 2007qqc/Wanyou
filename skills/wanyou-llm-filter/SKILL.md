---
name: wanyou-llm-filter
description: Apply keyword rules, LLM keep-drop decisions, summaries, and section transitions for Wanyou. Use when Codex needs to tune provider routing, explain why an item was kept or dropped, or debug summary quality.
---

# Wanyou LLM Filter

## Workflow

1. Check keyword rules in `config.py` first.
2. Confirm the active provider and model in `config.py`.
3. Use `wanyou/decider.py` for keep/drop behavior.
4. Use `wanyou/synthesizer.py` for summaries and transitions.
5. Keep `INTERACTIVE_REVIEW` off for one-run automation unless manual review is explicitly wanted.

## Debug Rules

- If the model is not called, inspect `LLM_ENABLED`, provider, and API key env names.
- If an undecided item is kept unexpectedly, inspect `DEFAULT_COPY_WHEN_UNDECIDED`.
- Use [references/llm-routing.md](references/llm-routing.md) for routing notes.
