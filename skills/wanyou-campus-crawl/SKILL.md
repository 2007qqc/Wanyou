---
name: wanyou-campus-crawl
description: 从单个校园来源采集万有 raw Markdown，覆盖公众号、公开站点与需登录站点。需要单独测某个爬虫模块、生成单来源 Markdown 预览，或在 LLM 合成与富文本导出之前排查抓取失败时使用。
---

# 万有校园抓取

## 用途

用它独立运行一个或多个爬虫模块，产出模块级 raw/final Markdown（以及可选 HTML）。

支持的模块：

- `wechat`：公众号信息（走微信读书，见下）
- `lib`：图书馆信息
- `hall`：新清华学堂
- `physics`：物理系学术报告
- `info`：教务通知，需要统一身份认证
- `myhome`：家园网信息，需要统一身份认证
- `public`：`lib hall physics wechat`
- `login`：`info myhome`
- `all`：全部模块

## 命令

只跑公众号并生成它的万有 Markdown/HTML：

```bash
python scripts/run_wanyou_module.py wechat
```

显式生成 Markdown 与富文本 HTML：

```bash
python scripts/run_wanyou_module.py wechat --with-richtext
```

只出 Markdown，不出富文本 HTML：

```bash
python scripts/run_wanyou_module.py wechat --md-only
```

分别跑各公开模块：

```bash
python scripts/run_wanyou_module.py lib
python scripts/run_wanyou_module.py hall
python scripts/run_wanyou_module.py physics
python scripts/run_wanyou_module.py wechat
```

跑需登录来源（共用清华统一认证）：

```bash
python scripts/run_wanyou_module.py info
python scripts/run_wanyou_module.py myhome
python scripts/run_wanyou_module.py login
```

跑全部公开来源：

```bash
python scripts/run_wanyou_module.py public
```

跑全部模块：

```bash
python scripts/run_wanyou_module.py all
```

等价的 skill 包装脚本：

```bash
python skills/wanyou-campus-crawl/scripts/run_wanyou_campus_crawl.py wechat
python skills/wanyou-campus-crawl/scripts/run_wanyou_campus_crawl.py public --md-only
```

## 公众号来源（微信读书）

公众号列表走**微信读书网页版**（`config.WECHAT_SOURCE = "weread"`，默认），
正文直连 `mp.weixin.qq.com`（免登录）。旧路线 `down.mptext.top` 的域名 2026-10-30
到期，只留作回滚：把 `WECHAT_SOURCE` 切回 `"mptext"` 即可，两条路线的下游完全一致。

抓取需要**一个带调试端口、已登录微信读书的 Chrome**：

- 脚本会自动用 `--remote-debugging-port=9333` + `WEREAD_PROFILE_DIR` 起一个专用实例
  （独立 profile，和你日常那个 Chrome 互不影响），已有在跑的实例则直接复用。
- **复用很关键**：登录态和人机校验的信任都留在那个窗口里，重启一次就得多过一次验证码。
- 首次或登录失效时会提示你扫码；弹出「安全检测」人机校验时，到那个 Chrome 窗口里
  手动完成即可，脚本会停下等。
- 目标号写在 `config.WEREAD_ACCOUNT_BOOK_IDS`（`MP_WXS_` + `base64decode(__biz)` 的数字部分），
  号名运行时从书架接口反查，不用手写。
- 密集请求会触发 `-2041`（人机校验）。真撞上了就停手，过完验证再跑。

## 调试规则

- 公众号报 `-2041`：多为腾讯防水墙的人机校验没过（页面显示「安全检测中」）。到那个
  Chrome 窗口里手动过一次，然后重跑，**不是接口下线**。
- 公众号报 `-2003`：请求参数格式错误（`errMsg` 会明写）。先核对实际发出去的 URL 和
  `bookId`，**不是限流**。这个码很容易被误判成风控，排查前先打印真实请求。
- 公众号报 `-2010 用户不存在`：登录态失效，在 Chrome 里重新扫码登录微信读书。
- 页面白屏、探针报 `blank`：触发风控。停手几小时，并且改掉反复新开标签页的习惯。
- 某个号一直取不到新文章：先在浏览器里手动打开那个号确认。微信读书对部分公众号的
  收录会滞后，属于平台侧行为。
- 一天发了好几篇却只取到一篇：检查有没有只读 `subReviews[0]`——微信读书是「一次群发
  = 一个条目，里面的 `subReviews` 才是逐篇文章」，`wanyou/weread_client.py` 已经展开。
- 需要登录的模块用 `login` 一起测，因为 `info` 与 `myhome` 共用一个统一认证浏览器会话。
- 只出 Markdown 用 `--md-only`；想在 LLM 合成前先看爬虫原始产物，用 `--raw-only --md-only`。
- 登录与选择器快照看 `output/module_<modules>_<timestamp>/debug/`。
