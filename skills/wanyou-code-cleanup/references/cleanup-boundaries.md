# Cleanup Boundaries

Use this reference when cleaning code touched by recent debugging.

## Xiumi Browser Automation

Preserve behavior before reducing code size:

- Start from `XIUMI_HOME_URL` and confirm login before creating a graphic draft.
- Avoid direct pre-login navigation to `paper/for/new`.
- Keep weak matching for `图文排版`, `新建图文`, `图文`, and `上传图片(无水印)` because Xiumi labels can vary.
- Write text before image upload. Upload images through `我的图库`, rewrite image URLs with Xiumi asset URLs, then apply final layout.
- Keep local image upload before `data:image/...` payloads; data URLs can trigger COS errors.
- Keep the browser open after save or exception until the user presses Enter.
- Move details to JSONL logs instead of printing upload attempts, selector candidates, tracebacks, or per-image URLs.

## LLM And Content Pipeline

Clean for fewer calls without reducing observability:

- Source pages/APIs produce raw Markdown.
- Ranked raw ranks and selects without LLM text cleaning.
- Final Markdown/HTML performs selection, formatting cleanup, and theme decoration.
- Preserve abstracts and necessary details for academic talks and table-like source content.
- If content appears missing, inspect raw and ranked raw before changing synthesis prompts.

## Environment And Output

- Keep `.env` and `.env.example` aligned when adding or renaming variables.
- Keep README environment examples in one consolidated setup section.
- Do not commit generated `output/` artifacts unless the user explicitly asks for fixtures.
- Prefer debug logs under `output/*debug*` over noisy stdout.

## Verification Ladder

Use the smallest check that can catch the likely breakage:

1. `python -m py_compile <changed python files>`
2. wrapper help or dry-run commands for CLI argument changes
3. local HTML regeneration for formatting/export changes
4. module-level crawler run for source parser changes
5. full run only after shared pipeline changes
6. live Xiumi or WeChat publishing only with explicit user approval
