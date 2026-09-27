"""微信读书（weread）公众号文章发现。

替代 down.mptext.top：用微信读书网页版列出公众号的群发历史，
正文仍走 mp.weixin.qq.com 直连（免登录）。

以下事实均为实测结论，改这个模块前先读一遍：

* 列表接口是 ``/web/mp/articles?bookId=&offset=``，**必须在阅读器页
  （``/web/mp/reader/<hash>``）的上下文里发**。换个页面背景发同样的请求会失败。
* 一次请求返回 20 个**群发**，一次群发里可能有多篇文章，必须展开
  ``reviews[].subReviews[]``，只取 ``subReviews[0]`` 会丢掉同次群发的其余文章。
* 只有 ``offset`` 有效，它跳过的是**群发条数**（不是文章篇数）；
  ``count`` / ``maxIdx`` 会被服务端忽略。
* ``readerUrl`` 尾部的 hash 每个号各不相同（前后缀是校验位），**不能自己拼**，
  只能从 ``/web/shelf/sync`` 返回的 ``deepLink`` 里取 ``?v=``。
* 拿到 ``-2041`` 基本就是撞上腾讯防水墙的人机校验（页面显示「安全检测中」）：
  让用户在打开的 Chrome 窗口里手动过一次就恢复，**不是接口下线**，也不是限流。
* ``-2003`` 的真实含义是**参数格式错误**（errMsg 会明写），最常见的原因就是
  bookId 没传对——**别照字面当成限流**，先核对实际发出去的 URL。
* ``originalId`` 里的 ``~`` 是 base64url 的下划线（weread 的 rid 用 ``_`` 做分隔符），
  还原成 ``_`` 才能拼出打得开的原文链接。
"""

import json
import pathlib
import re
import shutil
import subprocess
import time

import config

BOOK_ID_PREFIX = "MP_WXS_"

DEFAULT_PORT = 9333
DEFAULT_PROFILE_DIR = "output/selenium_cache/weread-debug-profile"

# 阅读器页就绪的判据：标题形如「<号名> - 公众号 - 微信读书」。
READER_TITLE_MARK = "公众号"


class WereadError(RuntimeError):
    """微信读书链路的通用错误。"""


class WereadLoginRequired(WereadError):
    """登录态失效，需要用户在浏览器里重新扫码。"""


class WereadRiskControl(WereadError):
    """撞上人机校验（-2041 / 验证码）。"""


PROBE_JS = """
  var txt = (document.body && document.body.innerText || '').replace(/\\s+/g, ' ').trim();
  var capSel = '[id*="captcha"], [class*="tcaptcha"], iframe[src*="captcha"]';
  var capVisible = [].slice.call(document.querySelectorAll(capSel)).some(function(n){
    for (var c = n; c; c = c.parentElement) {
      var s = getComputedStyle(c);
      if (s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity) === 0) return false;
    }
    var r = n.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  });
  var onReader = location.pathname.indexOf('/web/mp/reader/') === 0;
  var title = document.title || '';
  var verdict;
  if (capVisible) verdict = 'captcha';
  else if (!onReader) verdict = 'wrong_page';
  else if (title.indexOf('%s') >= 0) verdict = 'ready';
  else if (txt.length < 50) verdict = 'loading';
  else verdict = 'blank';
  return JSON.stringify({verdict: verdict, title: title, len: txt.length, cap: capVisible});
""" % READER_TITLE_MARK

SHELF_JS = """
  const cb = arguments[arguments.length - 1];
  fetch("/web/shelf/sync?synckey=0&teenmode=0&album=1", {credentials: "include"})
    .then(function(r){ return r.text() }).then(function(t){ cb(t) })
    .catch(function(e){ cb("ERR:" + e) });
"""

ARTICLES_JS = """
  const cb = arguments[arguments.length - 1];
  const url = "/web/mp/articles?bookId=" + encodeURIComponent(arguments[0])
            + "&offset=" + arguments[1];
  fetch(url, {credentials: "include"})
    .then(function(r){ return r.text() }).then(function(t){ cb(t) })
    .catch(function(e){ cb("ERR:" + e) });
"""

ADD_TO_SHELF_JS = """
  const cb = arguments[arguments.length - 1];
  fetch("/mp/shelf/addToShelf", {
    method: "POST", credentials: "include",
    headers: {"Content-Type": "application/json;charset=UTF-8"},
    body: JSON.stringify({bookIds: arguments[0]})
  }).then(function(r){ return r.text() }).then(function(t){ cb(t) })
    .catch(function(e){ cb("ERR:" + e) });
"""


def _chrome_candidates():
    return [
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]


def find_chrome():
    configured = str(getattr(config, "WEREAD_CHROME_PATH", "") or "").strip()
    if configured and pathlib.Path(configured).exists():
        return configured
    for candidate in _chrome_candidates():
        if candidate and pathlib.Path(candidate).exists():
            return candidate
    raise WereadError("找不到 Chrome，请在 config.WEREAD_CHROME_PATH 里指定可执行文件路径")


def _port_open(port, timeout=1.5):
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def ensure_debug_browser(port=None, profile_dir=None, wait_seconds=25):
    """确保有一个带调试端口、已登录微信读书的 Chrome 在跑。

    已经有一个在跑就直接复用——复用很关键：登录态和人机校验的信任都留在那个
    窗口里，重启一次就得多过一次验证码。
    """
    port = int(port or getattr(config, "WEREAD_DEBUG_PORT", DEFAULT_PORT) or DEFAULT_PORT)
    version = _port_open(port)
    if version:
        print(f"公众号：复用已在运行的调试 Chrome（端口 {port}，{version.get('Browser', '')}）")
        return port, profile_dir

    profile = profile_dir or getattr(config, "WEREAD_PROFILE_DIR", DEFAULT_PROFILE_DIR)
    profile_path = pathlib.Path(profile)
    profile_path.mkdir(parents=True, exist_ok=True)
    chrome = find_chrome()
    print(f"公众号：启动调试 Chrome（端口 {port}，profile {profile_path}）")
    subprocess.Popen(
        [
            chrome,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_path}",
            "--no-first-run",
            "--no-default-browser-check",
            "https://weread.qq.com/",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        time.sleep(1)
        if _port_open(port):
            return port, str(profile_path)
    raise WereadError(
        f"调试 Chrome 起不来（端口 {port} 没响应）。"
        "注意 Chrome 136 起在默认用户目录上会静默忽略 --remote-debugging-port，"
        "必须配 --user-data-dir。"
    )


def attach(port=None):
    """接管调试 Chrome（不新开浏览器，也不带自动化特征）。"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    port = int(port or getattr(config, "WEREAD_DEBUG_PORT", DEFAULT_PORT) or DEFAULT_PORT)
    options = Options()
    options.debugger_address = f"127.0.0.1:{port}"
    cache_dir = pathlib.Path(getattr(config, "SELENIUM_CACHE_DIR", "output/selenium_cache"))
    driver_path = cache_dir / "chromedriver" / "chromedriver.exe"
    service = Service(str(driver_path)) if driver_path.exists() else Service()
    driver = webdriver.Chrome(options=options, service=service)
    driver.set_script_timeout(45)
    return driver


def probe(driver):
    return json.loads(driver.execute_script(PROBE_JS))


def wait_reader_ready(driver, url, timeout=300):
    """导航到阅读器页并等它真正就绪；撞上人机校验就等用户手动过。"""
    driver.get(url)
    deadline = time.time() + timeout
    notified = False
    while time.time() < deadline:
        time.sleep(3)
        state = probe(driver)
        if state["verdict"] == "ready":
            return state
        if state["verdict"] == "captcha" and not notified:
            notified = True
            print(
                "公众号：微信读书弹出了人机校验（安全检测/选图），"
                "请到打开的 Chrome 窗口里手动完成，我会在这里等。"
            )
    raise WereadRiskControl(f"阅读器页 {timeout} 秒内没就绪（最后状态：{state['verdict']}）")


def _js_call(driver, script, *args):
    raw = driver.execute_async_script(script, *args)
    text = str(raw or "")
    if text.startswith("ERR:"):
        raise WereadError(f"页面内请求失败：{text[4:120]}")
    try:
        return json.loads(text)
    except ValueError as exc:
        raise WereadError(f"接口返回了非 JSON 内容：{text[:120]}") from exc


def list_shelf(driver):
    """列出书架里已订阅的公众号：号名 -> {bookId, readerUrl}。"""
    payload = _js_call(driver, SHELF_JS)
    if payload.get("errCode"):
        raise WereadLoginRequired(
            f"书架接口返回 {payload['errCode']}，通常是登录态失效或撞上人机校验"
        )
    shelf = {}
    for book in payload.get("books") or []:
        book_id = str(book.get("bookId") or "")
        if not book_id.startswith(BOOK_ID_PREFIX):
            continue
        match = re.search(r"[?&]v=([^&]+)", str(book.get("deepLink") or ""))
        shelf[str(book.get("title") or book_id)] = {
            "bookId": book_id,
            "readerUrl": f"https://weread.qq.com/web/mp/reader/{match.group(1)}" if match else "",
        }
    return shelf


def subscribe(driver, book_ids):
    """把公众号加进书架（幂等）。"""
    payload = _js_call(driver, ADD_TO_SHELF_JS, list(book_ids))
    if payload.get("errCode"):
        raise WereadError(f"订阅公众号失败：{payload.get('errCode')}")
    return payload


def fetch_account_articles(driver, book_id, reader_url, days_limit, max_pages=2):
    """抓一个公众号最近若干天的群发文章。"""
    wait_reader_ready(driver, reader_url)
    cutoff = time.time() - float(days_limit) * 86400
    items = []
    seen = set()
    for page in range(max(1, int(max_pages))):
        payload = _js_call(driver, ARTICLES_JS, book_id, page * 20)
        err_code = payload.get("errCode")
        if err_code:
            detail = payload.get("errMsg") or ""
            raise WereadRiskControl(
                f"文章列表接口返回 {err_code} {detail}（人机校验未过时就是这个，"
                "别被 errMsg 骗了——同一个 URL 过完验证会返回 200，"
                "请在打开的 Chrome 窗口里手动完成验证后重跑）"
            )
        groups = payload.get("reviews") or []
        if not groups:
            break
        oldest = None
        for group in groups:
            group_time = int(group.get("createTime") or 0)
            for sub in group.get("subReviews") or []:
                review = sub.get("review") or {}
                info = review.get("mpInfo") or {}
                title = str(info.get("title") or "").strip()
                if not title:
                    continue
                timestamp = int(review.get("createTime") or group_time or 0)
                original_id = str(info.get("originalId") or "")
                url = (
                    "https://mp.weixin.qq.com/s/" + original_id.replace("~", "_")
                    if original_id
                    else ""
                )
                if not url or url in seen:
                    continue
                seen.add(url)
                items.append(
                    {
                        "title": title,
                        "url": url,
                        "digest": str(info.get("digest") or ""),
                        "cover": str(info.get("cover") or ""),
                        "timestamp": timestamp,
                        "aid": None,
                        "mid": None,
                        "idx": None,
                    }
                )
                if timestamp and (oldest is None or timestamp < oldest):
                    oldest = timestamp
        print(f"公众号：{book_id} 第 {page + 1} 页取回 {len(groups)} 次群发，累计 {len(items)} 篇")
        if oldest is None or oldest < cutoff:
            break
        time.sleep(2)
    items.sort(key=lambda item: item.get("timestamp") or 0, reverse=True)
    return items


def collect_articles(days_limit=None, *, port=None, profile_dir=None, max_pages=None):
    """发现所有目标公众号最近若干天的文章（正文由调用方另行抓取）。"""
    days_limit = float(days_limit or getattr(config, "WECHAT_MAIN_RECENT_DAYS", 7) or 7)
    max_pages = int(max_pages or getattr(config, "WEREAD_MAX_PAGES", 2) or 2)
    book_ids = list(getattr(config, "WEREAD_ACCOUNT_BOOK_IDS", []) or [])
    if not book_ids:
        raise WereadError("config.WEREAD_ACCOUNT_BOOK_IDS 是空的，没有可抓的公众号")

    port, profile_dir = ensure_debug_browser(port, profile_dir)
    driver = attach(port)
    try:
        shelf = list_shelf(driver)
        print(f"公众号：书架里有 {len(shelf)} 个已订阅公众号")

        missing = [bid for bid in book_ids if bid not in {v['bookId'] for v in shelf.values()}]
        if missing:
            print(f"公众号：{len(missing)} 个公众号还没订阅，正在加入书架")
            subscribe(driver, missing)
            shelf = list_shelf(driver)

        by_book_id = {entry["bookId"]: (name, entry) for name, entry in shelf.items()}
        all_items = []
        for book_id in book_ids:
            found = by_book_id.get(book_id)
            if not found:
                print(f"公众号：跳过 {book_id}（书架里没有，可能是 bookId 失效）")
                continue
            name, entry = found
            if not entry.get("readerUrl"):
                print(f"公众号：跳过 {name}（拿不到阅读器页地址）")
                continue
            print(f"公众号：正在读取 {name} 的推送列表")
            items = fetch_account_articles(driver, book_id, entry["readerUrl"], days_limit, max_pages)
            for item in items:
                item["account_keyword"] = name
            all_items.extend(items)
        return all_items
    finally:
        # 只断开 chromedriver，不关浏览器——登录态和人机校验的信任都留在那个窗口里。
        try:
            driver.service.stop()
        except Exception:
            pass


if __name__ == "__main__":
    # 只做发现，不下正文，方便单独验证这条链路。
    for entry in collect_articles():
        print(entry["title"])
