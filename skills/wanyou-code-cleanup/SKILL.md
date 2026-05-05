---
name: wanyou-code-cleanup
description: Clean Wanyou code after bug fixes or feature spikes. Use when Codex is asked to remove dirty code, stale debug prints, duplicated logic, dead branches, overgrown helper functions, repeated LLM cleaning/filtering calls, or temporary Selenium/Xiumi upload scaffolding while preserving verified behavior.
---

# Wanyou Code Cleanup

## Core Rule

Clean only after understanding the behavior that must survive. Prefer deleting stale scaffolding, merging duplicate helpers, and moving noisy diagnostics to logs over broad rewrites.

## Workflow

1. Read the recent diff and relevant call path before editing.
2. Identify the user-visible contract: inputs, outputs, files written, browser behavior, and terminal output.
3. Classify cleanup candidates:
   - safe: dead code, duplicate constants, stale prints, unused variables, unreachable branches
   - risky: timing-sensitive Selenium steps, source parsing, LLM prompts, output schema, environment loading
4. Make small scoped edits with `apply_patch`.
5. Preserve existing fallbacks unless a newer verified path fully replaces them.
6. Run the narrowest useful verification first, then broaden only when the touched surface is shared.
7. Report what was removed, what was intentionally kept, and which verification ran.

## Wanyou-Specific Checks

- Keep `.env`-based configuration as the single user-editable environment path.
- Avoid reintroducing extra LLM cleaning passes. Ranking can score and select; final generation is the normal cleanup layer.
- Keep raw/ranked raw as inspection artifacts and avoid truncating source details unless a prompt or explicit output policy requires it.
- Keep Xiumi's verified order: login from My Xiumi, create graphic draft, write text, upload images, apply final layout, save, then wait for user Enter before closing.
- Keep Xiumi stdout concise. Detailed selector/upload diagnostics should go to `output/xiumi_debug/*.jsonl`.
- Do not remove cross-platform branches just because the current machine is macOS.

For fragile areas, read `references/cleanup-boundaries.md` before editing.
