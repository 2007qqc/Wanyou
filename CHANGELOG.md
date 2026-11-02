# 更新日志

## 2026-11-02 · 第 7 周出刊与公众号链路增强

### 代码组织

- 合并 `optimize/code-cleanup` 的代码整理结果：去掉重复逻辑，抽公共 Markdown 解析
  （`wanyou/markdown_document.py`），把公众号「要点透视 / 摘要」逻辑独立到
  `wanyou/wechat_brief.py`，`wechat_pipeline.py` 相应精简。
- 统一日期格式化工具 `utils_dates.format_datetime_text`，公众号和调试日志共用。

### 公众号正文与报名二维码

- 新增微信读书整篇正文抓取：列表项带 `review_id`，逐条请求
  `/web/mp/content?reviewId=...`，取 `.rich_media_content` 的正文与图片；列表接口
  只给节选的限制不再影响时效判断和摘要质量（`weread_client.fetch_article_contents`）。
- 新增 `wanyou/wechat_qr.py`：从正文图片里按上下文筛二维码，用 OpenCV 解码/检测
  （带中心 logo 的群二维码用定位点 + 黑白占比兜底），落地到 `output/wechat_qr/`，
  最多每条 2 张；成稿在「摘要」后、「内容:」前插入 `![报名二维码](...)`。
- 公众号卡片不再写推送日期/发布时间（`wechat_pipeline.write_md_stream`）；`raw_ranker`
  对公众号栏目跳过发布日期二次过滤，避免把活动日期误当发布日期。

### 时效与选稿规则

- 修复「烛光计划」类招募被误丢：闸门日期解析改用正文全文（前 4000 字），LLM 判断
  传入真实发布时间；活动/报名日期只在正文里的推送不再因 `unknown` 被丢。
- 截止日正好是见刊日（次周周一）的不再保留：`temporal_filter` 返回
  `deadline_on_publish_day`，公众号闸门同步同一判断。
- 不在本期窗口（`WANYOU_RUN_DATE` 起）发布的公告不选：新增
  `utils_issue_filter.published_in_current_window`，教务/家园网/图书馆开馆类公告在
  爬虫阶段丢弃（`published_before_window`）；活动类来源不受此限。
- 物理系学术报告卡片只写 `报告时间`，不再写页面发布日期（`crawlers_physics`）。

### 图片路径修复

- `utils_html._strip_residual_markup` 在去 Markdown 斜体前整体保护图片语法，避免
  `_wanyou_…` / `_hall_…` 这类路径被当强调标记删掉下划线，导致 H5/DOCX/秀米丢图。
- `image_paths.clean_markdown_image_target` 不再把绝对 Windows 路径里的 `\_` 当作
  Markdown 转义删除，修复秀米 `cdn_missing`（`images\_wanyou_...` 被拼成
  `images_wanyou_...`）。

### 依赖与文档

- `requirements.txt` 增加 `numpy`、`opencv-python-headless`（二维码识别用；缺依赖时
  自动停用，不会误贴普通配图）。
- README / AGENTS 同步公众号全文抓取、二维码、三条内容规则和图片路径注意事项。

### 验证

- 要点速递覆盖自检：样本 17 条 / 17 条要点透视（936 字）、正式稿 18 条 / 18 条
  要点透视（850 字）全部进入 LLM 提示词（上限 4000 字，未截断），没有选入信息被漏掉；
  因此本次不改 `_build_highlights`，只补更新日志。
- 全部 `wanyou/*.py` 编译与模块 import 通过。

### 产物

- 第 7 周本地正式稿最新版：`output/week7_20261102/`（9 栏目 18 条，含 8 张二维码）。
- 新规则样本：`output/sample_20261102/`（8 栏目 17 条，物理系无发布日期、公众号无
  推送日期；样本说明见该目录 `NOTES.md`）。
- 秀米草稿 735875325 仍是上一版（19 条），需要覆盖时再推一次。
