# Xiumi Draft Workflow

This repository uses Xiumi as a browser-operated draft editor. Keep the workflow below stable unless a new manual test proves Xiumi has changed.

## Canonical Order

1. Confirm login from `XIUMI_HOME_URL`.
2. If the user is not logged in, wait for manual login and then continue automatically.
3. Enter `图文排版` from `我的秀米`; do not open `paper/for/new` before login is confirmed.
4. Create or enter a new graphic draft.
5. Write text first: convert the final Markdown/HTML into Xiumi-friendly HTML, replace image tags with temporary placeholders, and set the editor body.
6. Upload images second: open `我的图库`, use the `上传图片(无水印)` image input, and batch-upload local body images when the input supports multiple files. Fall back to single-image upload only when a batch cannot be confirmed.
7. Prefer local image files before `data:image/...` payloads. Inline data images can trigger Xiumi COS failures and should not block normal local images.
8. Apply final layout last: replace original image sources with Xiumi asset URLs, remove or mark any images that did not upload, and set the editor body again.
9. Save the draft, print the draft URL when available, and keep the browser open for user editing until the user presses Enter in the command line.

## Debug Notes

- `filesLength=0` after dispatch is not enough to prove failure. Xiumi may clear the file input immediately after upload processing starts.
- Treat a new `img.xiumi.us` or `/xmi/ua/` source as the successful upload signal.
- If Xiumi shows `上传失败[cos]`, inspect whether the failing item is a converted data URL or a normal local file.
- After at least one successful upload, a later single-image timeout should not abort the whole batch; skip or mark that image and continue with the rest.
- The upload probe should use a harmless generated test image and should not upload real Wanyou content unless the user explicitly approves the run.
- Keep standard output concise: login state, editor entry, text/image/layout stages, save status, and final URL. Put selector details, upload attempts, timeouts, and tracebacks in `output/xiumi_debug/*.jsonl`.
