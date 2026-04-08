# Wanyou

清华大学物理系“万有预报”自动生成项目。

## 功能概览

当前流程支持：
- 校内站点信息抓取
- 统一认证登录与共享浏览器会话
- 公众号抓取与摘要输出
- LLM 辅助清洗、摘要、时效判断
- Markdown / HTML / Browser Agent payload 导出

## 环境要求

- Python 3.10+
- Microsoft Edge
- Edge WebDriver
- 如需导出 DOCX，还需要本机安装 `pandoc`

安装依赖：
```powershell
python -m pip install -r requirements.txt
python -m pip install PyYAML
```

## 快速运行

仅运行公开源站：
```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --public-only --skip-docx
```

运行完整流程：
```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login
```

## 登录与二次认证

程序现在只做一次清华统一认证，然后复用同一个 Edge 会话抓取教务和家园网。

如果统一认证进入二次认证：
1. 程序会保留可见的 Edge 浏览器窗口
2. 用户在浏览器中手动完成验证
3. 回到终端按回车
4. 程序继续抓取

## 日期筛选规则

### 默认时间阈值

默认情况下，程序会把“运行此程序时刻往前推 7 天”作为时间阈值。

例如：
- 如果你在 `2026-04-08 15:30` 运行
- 默认阈值就是 `2026-04-01 15:30`
- 早于这个时间的信息，会尽量在抓取详情页之前被跳过

### 用户自定义时间阈值

可以在 [config.py](./config.py) 中配置：

```python
NOTICE_PREFILTER_CUTOFF = "2026-04-01 00:00"
```

优先级规则：
- 如果 `NOTICE_PREFILTER_CUTOFF` 为空，使用“当前运行时刻往前 7 天”
- 如果 `NOTICE_PREFILTER_CUTOFF` 有值，优先使用你指定的时间

### 前置过滤行为

程序会尽量在“抓正文前”做过滤：
- 如果列表页已经能看到可用时间戳，就先按时间阈值判断
- 如果标题已经出现在上一期万有预报中，也会直接跳过
- 只有列表页看不出时间时，才会继续抓详情页

### 上一期去重

程序会自动读取上一份 `wanyou_YYYYMMDD_HHMM.md`，同栏目里已经出现过的标题，本期默认不再重复进入筛选。

## 当前栏目行为

- `教务通知`
  - 已适配新版教务通知页
  - 如果页面成功打开但本期没有符合时间窗口的新通知，会按“本期无有效新通知”处理
- `家园网信息`
  - 复用统一认证会话抓取
  - 优先在列表层按时间过滤
- `图书馆信息`
  - 优先按列表可见日期或活动日期过滤
- `新清华学堂`
  - 过期活动或上一期已出现的活动，不再下载海报
- `物理系学术报告`
  - 先按列表时间和上一期标题过滤
  - 如果本期没有新增报告，按“本期暂无新增报告”处理
- `公众号信息`
  - 先按 API 自带时间戳和上一期标题过滤
  - 只有保留下来的文章才继续抓正文和生成摘要

## LLM 相关

默认配置在 [config.py](./config.py)：

```python
LLM_ENABLED = True
LLM_PROVIDER = "deepseek"
LLM_MODEL = "deepseek-chat"
```

所有涉及 LLM 的步骤都会输出更细的进度提示，例如：
- `等待LLM输出中：正在判断教务通知条目时效`
- `等待LLM输出中：正在压缩单条信息篇幅`
- `等待LLM输出中：正在总结公众号内容`
- `等待LLM输出中：正在提取学术报告字段`

## 公众号抓取

公众号抓取使用 `down.mptext.top` API，不直接登录微信。

需要设置：
```powershell
$env:WECHAT_PUBLIC_API_KEY = "your-key"
```

## 调试与输出

每次运行会在 `output/<timestamp>/` 生成产物。

重点目录：
- `*_raw.md`
- `*.md`
- `*.html`
- `debug/`

## 推荐使用策略

1. 正常周更场景下，保持 `NOTICE_PREFILTER_CUTOFF = ""`
2. 只有在补历史稿、重跑某一期或需要手动改变时间窗口时，再设置 `NOTICE_PREFILTER_CUTOFF`
3. 如果某个栏目提示“本期无新增信息”，优先检查是否被时间阈值或上一期去重过滤掉
4. 真正的结构性问题，通常会伴随页面快照、选择器失败或 `debug/` 诊断文件

## 已知问题

- 某些源站列表页完全不提供可解析时间，仍需要进入详情页
- 统一认证遇到更复杂的二次认证时，仍需要人工接管
- DOCX 导出仍然依赖本机 `pandoc`
