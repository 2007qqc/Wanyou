# 富文本产物备注

- Markdown 是唯一的事实来源。
- HTML 导出走 `generators/h5_generator.py`。
- browser-agent payload 导出走 `generators/browser_agent.py`。
- DOCX 导出依赖本机的 `pandoc`。

## HTML 是单文件自包含产物

- 页面本体（主题渲染）与复制源（`generators/wechat_inline.py`）两条渲染路径的 `<img>` 都要内联成 `data:`。
  只内联复制源不够：页面本体会写相对路径，HTML 一移动就整页断图。
- 内联由 `wanyou/inline_images.py::embed_local_images` 完成，最长边压到 900px（原图合计十几 MB 时仍能把产物控制在 1–2 MB）。
- 验收标准：`skills/wanyou-richtext-export/scripts/run_wanyou_richtext_export.py` 打印的
  `html_images: ... local=0` 与 `html_self_contained: yes`。`local` 非零时脚本退出码为 1。
- 已知会导致 `local` 非零的原因：Markdown 吃掉了路径里的下划线（`module_lib_YYYYMMDD_HHMM` → `modulelibYYYYMMDDHHMM`），
  H5 生成器于是把不存在的路径原样写进 `src`。先跑 `scripts/prepare_xiumi_markdown.py` 再导出。

## 页头元信息

- 页头只剩三样：横幅图（仓库根目录 `badge.jpg`，固定文件名）、标题、一行元信息。
- 元信息 = 生成时间 +（能拿到时的）校历周次，实现在 `wanyou/academic_calendar.py`。
- 周次靠 info 教务通知的「第N周（周X）」+ 正文日期做锚点运算，**不用视觉模型读校历大图**（会把第 8 周读成第 4 周）。
- 取不到就只输出生成时间。同日缓存 `output/.cache/academic_week.json`；`WANYOU_ACADEMIC_WEEK=off` 关掉整段逻辑。
