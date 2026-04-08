# Wanyou

清华大学物理系“万有预报”自动化生成项目。

当前流程已经覆盖：
- 校园站点抓取
- 统一认证登录源抓取
- LLM 筛选、摘要、格式清洗
- Markdown / H5 HTML / Browser Agent payload 导出

## 运行环境

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

公开站点 smoke test：

```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --public-only --skip-docx
```

包含统一认证登录源的完整运行：

```powershell
python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --with-login
```

## 登录与二次认证

### 统一认证输入

运行带登录源的流程时，程序会提示输入一次清华统一认证用户名和密码。

- 默认复用同一套统一认证账号给 `教务通知` 和 `家园网信息`
- 密码输入时会回显 `·`
- 不会明文显示密码

### 共享浏览器会话

登录源现在改成了：

1. 只打开一个 Edge 浏览器会话
2. 只做一次统一认证
3. 登录成功后复用同一个浏览器继续抓取 `教务通知` 和 `家园网信息`

这可以避免两个栏目分别重复登录，减少统一认证流程冲突。

### 二次认证人工接管

如果统一认证进入二次认证页，程序当前采用半自动方式：

1. 自动弹出可见的 Edge 浏览器
2. 用户在浏览器中手动完成统一认证或二次认证
3. 回到终端按回车
4. 程序继续抓取教务和家园网信息

如果浏览器本来就已经有有效登录态，程序会直接复用，不再重复找登录按钮。

## 调试输出

程序现在会输出更适合调试的进度信息，例如：

- `正在打开统一认证浏览器会话`
- `正在提交统一认证账号密码`
- `统一认证登录成功`
- `成功登录教务，正在获取信息`
- `成功登录家园网，正在获取信息`
- `等待LLM输出中`

所有涉及 LLM 的步骤都会提示 `等待LLM输出中`，包括：

- 抓取正文格式清洗
- 公众号摘要
- 物理学术报告提取
- 栏目过渡语 / 摘要生成
- 教务页面结构诊断

## Debug 文件

每次运行产物在：

```text
output/<timestamp>/
```

重点调试目录：

```text
output/<timestamp>/debug/
```

常见文件包括：

- `shared_login_attempt.txt`
- `shared_after_login.html`
- `shared_after_manual_auth.html`
- `info_after_login.html`
- `info_after_open_teaching.html`
- `info_llm_hint.json`
- `myhome_after_login.html`

其中：

- `shared_login_attempt.txt` 会记录用户名长度、密码长度、密码哈希、SM2 加密长度、指纹字段长度等
- `info_llm_hint.json` 会在教务新版页面列表为空时，保存 LLM 基于页面 HTML/JS 给出的结构诊断

## 当前支持的栏目

- 教务通知
- 家园网信息
- 图书馆信息
- 新清华学堂
- 物理系学术报告
- 学生会信息
- 青年科协信息
- 学生社团信息
- 学生公益信息
- 其他公众号信息

## 公众号抓取

公众号抓取使用 `down.mptext.top` API，不直接登录微信。

需要的环境变量：

```powershell
$env:WECHAT_PUBLIC_API_KEY = "your-key"
```

独立运行：

```powershell
python wechat_public.py
```

当前行为：

- 先抓取正文
- 再用 LLM 生成短摘要
- 最终 Markdown 默认只写摘要，不再直接铺全文

## LLM 相关

当前默认模型配置在 `config.py`：

```python
LLM_ENABLED = True
LLM_PROVIDER = "deepseek"
LLM_MODEL = "deepseek-chat"
```

常用环境变量示例：

```powershell
$env:DEEPSEEK_API_KEY = "your-key"
$env:OPENAI_API_KEY = "your-key"
$env:GEMINI_API_KEY = "your-key"
$env:ZHIPUAI_API_KEY = "your-key"
$env:OCR_SPACE_API_KEY = "your-key"
```

## 最近新增功能

相较于之前版本，最近新增或重构了这些功能：

- 统一认证登录源改为共享同一个已认证 Edge 会话
- 支持二次认证的半自动人工接管
- 登录过程新增明确进度提示
- LLM 调用统一新增 `等待LLM输出中`
- 抓取正文新增 LLM 格式清洗
- 公众号输出从全文改为摘要优先
- 学术报告新增乱码清洗与字段提取
- 家园网正文标题层级自动降级，避免和栏目标题打平
- 教务新版页面新增备用入口与 LLM 结构诊断兜底
- 输出缺失栏目时自动补齐占位卡片和错误原因

## 已知问题

- 教务通知页面已经升级为新版前端，当前虽然能进入 `教务通知` 栏目，但有时列表仍为空，仍需继续适配前端数据加载方式
- 如果统一认证触发更复杂的二次认证流程，目前仍需用户手动接管浏览器
- DOCX 导出依赖本机 `pandoc`

## 产物

默认输出目录：

```text
output/<timestamp>/
```

可能生成：

- `wanyou_<timestamp>_raw.md`
- `wanyou_<timestamp>.md`
- `wanyou_<timestamp>.html`
- `wanyou_<timestamp>_agent.json`
- `wanyou_<timestamp>.docx`

## 排查建议

推荐调试顺序：

1. 先看 `debug/` 下的统一认证和页面快照
2. 再看 `raw.md`
3. 最后看 `final .md / .html`

如果登录源失败，请优先核对：

1. 是否真的进入了统一认证成功后的页面
2. 是否触发了二次认证
3. `shared_login_attempt.txt` 里的 `probe_sm2pass_length` 与 `probe_finger_gen_print_length`
4. `info_llm_hint.json` 是否给出了新版教务页面的额外线索
