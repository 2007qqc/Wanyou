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

## Xiumi Editor Publish Pitfalls (2026-08, verified against real drafts)

These behaviors were confirmed with real drafts. Read before touching editor-write logic in `scripts/publish_xiumi_draft.py`.

### Direct innerHTML injection saves but never renders → empty draft

- The Xiumi editor is an Angular app. The rendering layer is `comps.items`; content injected via `innerHTML=` or `scope.cell.text=` lands in `_qiBlock.items` (frozen layer — it saves but never renders).
- Symptom: save reports success, the draft URL exists, but the body opens empty.
- Fix: **trusted paste**. `navigator.clipboard.write([new ClipboardItem({'text/html': blob, 'text/plain': blob})])` → focus `[contenteditable]` → CDP `Input.dispatchKeyEvent` Ctrl+V (`modifiers:2, key:"v", code:"KeyV", windowsVirtualKeyCode:86`). This makes Xiumi's own paste handler build rendering-layer components under `comps.items`.
- Verify: open the draft and check the `/data/editing` response (or `output/parse_verify.py`) — rendered content must be in `comps.items`, not `_qiBlock`.

### CDP prerequisites

```python
browser.execute_cdp_cmd("Browser.grantPermissions", {
  "permissions": ["clipboardReadWrite", "clipboardSanitizedWrite"],
  "origin": "https://xiumi.us"})
browser.execute_cdp_cmd("Emulation.setFocusEmulationEnabled", {"enabled": True})
```

### Persistent-profile recover dialog blocks the editor

The editor may pop a "上次没有保存到服务器，是否恢复?" dialog that blocks editing. It must be dismissed (click 取消/确定). Handled automatically by `_dismiss_xiumi_recover_dialog`.

### Clear-then-paste is idempotent, but re-pasting identical content clears the draft

- Clear = Ctrl+A + Delete, then re-paste; only the last content survives (verified).
- Gotcha: when the HTML has no images, `final_html == text_first_html`, so the second clear+paste wipes the already-rendered content → empty draft. `_fill_xiumi_body_then_images` guards with `if final_html != text_first_html:` to skip the second paste.

### Paste handler strips all inline styles

- Only `text-align:justify` survives; `<h1>/<h2>/<h3>` map to semantic font-size 180%/140%/120%; adjacent blocks merge into ONE text component.
- Paste cannot preserve colors/backgrounds/borders. To keep the full source design, use the `--preserve-styles` model-build mode below instead of paste.

### Preserve full design styles with `--preserve-styles` (model-build mode)

Paste strips styles, but writing styles directly into the model preserves them — render, save, and the exported preview HTML all keep colors/backgrounds/borders/fonts/gradients/circular badges verbatim (verified on drafts 717852476, 717852825).

```powershell
python scripts/publish_xiumi_draft.py "xxx.html" --title "标题" --preserve-styles
```

- Parse each TOP-LEVEL `<section>` of the source into one block: the section's inline CSS (camelCased) goes into `comps.items[].txt1.style`; the inner HTML (paragraphs/spans with their inline styles) goes into `txt1.text`.
- Convert nested `<section>`/`<div>` to `<p>` (keep their style; the browser's HTML parser auto-closes nested `<p>`), drop empty `<p></p>` artifacts.
- Flow: seed paste → replace `layer.comps.items` inside `scope.$apply` → mark dirty → save.
- Reach the model: `window.angular.element(contenteditable).scope()._$.pages[0].layers[0].comps.items`.
- Comp schema: `{_comp:{constraint:{opMenu:{"text-merged":true},pose:{resize:"h"}},pose:{position:"static",width:null,height:null},style:{},tplId:"paper-cp:header/1-txt-normal",_$uuid:"comp-xxx"}, txt1:{type:"text",text:"<p style=...>...</p>",style:{camelCase CSS}}}`
- Text-only content; if images are detected it falls back to the base paste flow.

### Preserve heading hierarchy with `_promote_headings_for_xiumi`

- Inline `font-size` on large `<p>` gets stripped. Promote large paragraphs to semantic tags first: size≥34→`<h1>`, ≥20→`<h2>`, ≥17+bold→`<h3>` (keeps `text-align`, adds `letter-spacing:2px` to h1/h2).
- Pass `--no-base-format` to use heading promotion (default base formatting normalizes to 14px/18px and squashes custom large typography).

### PowerShell env vars are not inherited

The PowerShell tool does not inherit bash env vars — set `$env:WANYOU_SELENIUM_BROWSER='chrome'` in every command. Bash sandbox blocks win32 APIs; use PowerShell for win32 operations.

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
