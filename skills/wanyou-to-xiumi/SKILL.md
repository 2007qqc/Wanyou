---
name: wanyou-to-xiumi
description: Run the full Wanyou pipeline and push the final result into a Xiumi draft in one step. Use when Codex needs to produce a finished Xiumi 秀米草稿 from scratch, or when already-built output files need to be published to Xiumi.
---

# Wanyou to Xiumi Draft

## Purpose

One command from zero to a saved Xiumi draft. The full pipeline runs: campus crawlers (with optional unified login) + LLM ranking/selection + richtext generation + Xiumi editor automation (text, images, save). Also supports publishing existing output files to Xiumi without re-running crawlers.

## Workflow

```text
网页和公众号来源
  -> raw Markdown
  -> LLM 评测重要性的 ranked raw
  -> 清洗、选优、合成万有预报本地 Markdown 和 HTML
  -> 秀米草稿
```

The pipeline order inside Xiumi: write text (with image placeholders) -> upload images to "我的图库(无水印)" -> rewrite image URLs -> apply final layout -> save.

## Commands

### One-step: full pipeline + Xiumi draft

From zero to a saved Xiumi draft in one command:

```powershell
python scripts/run_wanyou_to_xiumi_draft.py --with-login --skip-docx
```

Public sources only (no unified login):

```powershell
python scripts/run_wanyou_to_xiumi_draft.py --public-only --skip-docx
```

With a custom title:

```powershell
python scripts/run_wanyou_to_xiumi_draft.py --with-login --skip-docx --title "万有预报"
```

Dry run (fill editor but do not click save, useful for verifying content before publishing):

```powershell
python scripts/run_wanyou_to_xiumi_draft.py --with-login --skip-docx --xiumi-dry-run
```

Skip WeChat to avoid API dependency:

```powershell
python scripts/run_wanyou_to_xiumi_draft.py --with-login --skip-wechat --skip-docx
```

Use a custom cover image:

```powershell
python scripts/run_wanyou_to_xiumi_draft.py --with-login --skip-docx --xiumi-cover badge.png
```

Keep the browser profile across runs:

```powershell
python scripts/run_wanyou_to_xiumi_draft.py --with-login --skip-docx --xiumi-profile-dir output/selenium_cache/my-xiumi-profile
```

### Standalone: publish existing output to Xiumi

When the pipeline has already run and you have final `.html` + `.md` files:

```powershell
python scripts/publish_xiumi_draft.py output/xxx/wanyou_xxx.html --markdown output/xxx/wanyou_xxx.md --title "万有预报"
```

Standalone dry run:

```powershell
python scripts/publish_xiumi_draft.py output/xxx/wanyou_xxx.html --markdown output/xxx/wanyou_xxx.md --dry-run
```

## Xiumi Image Control

| `XIUMI_IMAGE_MODE` | Behavior |
|---|---|
| `upload` (default) | Upload local images to Xiumi gallery, rewrite URLs, then apply final layout. Best quality. |
| `inline` | Convert local images to base64 data URLs inline. Larger HTML but no upload step. |
| `auto` | Try inline; fall back to omit if HTML exceeds `XIUMI_MAX_INLINE_IMAGE_HTML_CHARS`. |
| `omit` | Remove all images and leave placeholders. Fastest but no images in draft. |

Set in `.env`:

```ini
XIUMI_IMAGE_MODE=upload
XIUMI_MAX_INLINE_IMAGE_HTML_CHARS=900000
```

## Debug Rules

- If the script fails before Xiumi, inspect the output directory for intermediate artifacts (`*_raw.md`, `*_ranked_raw.md`, `*_todo_selected_raw.md`, `*.md`, `*.html`).
- If Xiumi login fails or is not detected, look for `output/xiumi_debug/*.jsonl` for upload/login diagnostics. The browser is kept open on error — check the browser window directly.
- If image upload fails for all images (consecutive failures >= `XIUMI_IMAGE_UPLOAD_MAX_FAILURES`), the script aborts image upload and leaves placeholders. Check `output/xiumi_debug/*.jsonl` for upload probe results.
- If individual images fail to upload, they are skipped and replaced with a "[配图上传未完成]" placeholder rather than blocking the whole draft.
- If the editor save state is "uncertain", the draft may still have been saved — check the editor URL in the browser. The browser window is kept open after save for manual verification.
- If the Xiumi page structure changes (new UI layout, changed CSS selectors), the inline JavaScript heuristics may fail. Check `output/xiumi_debug/*.jsonl` for `xiumi_create_failed`, `xiumi_login_not_settled`, or `file_input_missing` entries.
- If the script enters an editor but text is not applied, the `contenteditable` / Angular scope detection may need updating — check `xiumi_body_text_model_applied` in the debug log.
- Use `--xiumi-dry-run` to test the pipeline output without actually saving a draft, avoiding orphan drafts in Xiumi.
- Use `--skip-wechat` when testing to avoid failures from `WECHAT_PUBLIC_API_KEY` being expired or invalid.
- The browser profile is cleaned up by default after the browser closes. To preserve the profile (e.g. to keep login session), pass `--xiumi-profile-dir` with an explicit path.
- `output/xiumi_debug/*.jsonl` is the primary diagnostics target for Xiumi automation issues. Look there before changing `scripts/publish_xiumi_draft.py`.
