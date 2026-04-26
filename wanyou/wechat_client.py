import datetime
import html
import os
import sys
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse

import requests

import config


def _format_wechat_api_error(ret, err_msg):
    key_env = getattr(config, "WECHAT_PUBLIC_API_KEY_ENV", "WECHAT_PUBLIC_API_KEY")
    message = str(err_msg or "").strip()
    lower_message = message.lower()
    if ret == -1:
        return f"公众号 API 认证失败，请检查环境变量 {key_env} 是否有效"
    if ret in {401, 403}:
        return f"公众号 API 无权限访问，请检查环境变量 {key_env} 的权限配置"
    if ret == 200003 or "invalid session" in lower_message:
        return (
            f"公众号 API 会话无效或已过期，请重新设置环境变量 {key_env}，"
            "或重新获取 down.mptext.top 的有效 session/key 后再运行"
        )
    if message:
        return f"{message} (ret={ret})"
    return f"公众号 API 返回错误 (ret={ret})"


def _get_user_env(name):
    if not name or not sys.platform.startswith("win"):
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _value_type = winreg.QueryValueEx(key, name)
            return str(value or "").strip()
    except OSError:
        return ""


def _get_public_api_key():
    key_env = getattr(config, "WECHAT_PUBLIC_API_KEY_ENV", "WECHAT_PUBLIC_API_KEY")
    return os.environ.get(key_env, "").strip()

def normalize_url(url):
    if not url:
        return None
    url = html.unescape(str(url)).replace("&amp;", "&").strip()
    if not url:
        return None
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return "https://mp.weixin.qq.com" + url
    return url


def canonicalize_url_for_dedupe(url):
    if not url:
        return ""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    ignore_keys = {
        "sn",
        "chksm",
        "scene",
        "srcid",
        "sharer_shareinfo",
        "sharer_shareinfo_first",
        "clicktime",
        "ascene",
        "from",
        "version",
        "pass_ticket",
    }
    stable_query = {}
    for key, values in query.items():
        if key in ignore_keys or not values:
            continue
        stable_query[key] = values[0]
    normalized_query = urlencode(sorted(stable_query.items()))
    cleaned = parsed._replace(query=normalized_query, fragment="")
    return urlunparse(cleaned)


def parse_timestamp(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        value = int(value)
        return value if value > 0 else None

    text = str(value).strip()
    if not text:
        return None

    if text.isdigit():
        num = int(text)
        return num if num > 0 else None

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return int(datetime.datetime.strptime(text, fmt).timestamp())
        except ValueError:
            continue
    return None


def create_api_session():
    session = requests.Session()
    key_env = getattr(config, "WECHAT_PUBLIC_API_KEY_ENV", "WECHAT_PUBLIC_API_KEY")
    api_key = _get_public_api_key()
    session.headers["X-Auth-Key"] = api_key
    return session


def get_wechat_account_keywords():
    keywords = getattr(config, "WECHAT_ACCOUNT_KEYWORDS", None)
    if keywords:
        return [keyword.strip() for keyword in keywords if keyword and keyword.strip()]
    keyword = getattr(config, "WECHAT_ACCOUNT_KEYWORD", "").strip()
    return [keyword] if keyword else []


def _api_get_json(session, endpoint, params, timeout):
    base_url = getattr(config, "WECHAT_PUBLIC_API_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        raise ValueError("请在 config.py 设置 WECHAT_PUBLIC_API_BASE_URL")

    query = urlencode(params or {}, doseq=True)
    url = f"{base_url}/{endpoint.lstrip('/')}"
    if query:
        url = f"{url}?{query}"

    def request_json(auth_key):
        headers = {"X-Auth-Key": auth_key or ""}
        resp = requests.request("GET", url, headers=headers, data={}, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    auth_key = session.headers.get("X-Auth-Key", "")
    data = request_json(auth_key)
    if isinstance(data, dict):
        base_resp = data.get("base_resp")
        if isinstance(base_resp, dict):
            ret = base_resp.get("ret")
            if isinstance(ret, int) and ret != 0:
                key_env = getattr(config, "WECHAT_PUBLIC_API_KEY_ENV", "WECHAT_PUBLIC_API_KEY")
                user_key = _get_user_env(key_env)
                if ret == -1 and user_key and user_key != auth_key:
                    print(f"公众号 API 当前进程环境变量认证失败，已改用用户级 {key_env} 重试。")
                    session.headers["X-Auth-Key"] = user_key
                    retry_data = request_json(user_key)
                    retry_base_resp = retry_data.get("base_resp") if isinstance(retry_data, dict) else None
                    retry_ret = retry_base_resp.get("ret") if isinstance(retry_base_resp, dict) else None
                    if retry_ret == 0:
                        return retry_data
                    data = retry_data
                    base_resp = retry_base_resp if isinstance(retry_base_resp, dict) else base_resp
                    ret = retry_ret if isinstance(retry_ret, int) else ret
                err_msg = base_resp.get("err_msg") or "API 返回错误"
                raise RuntimeError(_format_wechat_api_error(ret, err_msg))
    return data


def _find_first_list(obj):
    if isinstance(obj, list):
        return obj
    if not isinstance(obj, dict):
        return []

    for key in ("list", "items", "records", "accounts", "articles", "article"):
        value = obj.get(key)
        if isinstance(value, list):
            return value

    for value in obj.values():
        if isinstance(value, list):
            return value
    return []


def _first_value(d, *keys):
    if not isinstance(d, dict):
        return None
    for key in keys:
        value = d.get(key)
        if value not in (None, ""):
            return value
    return None


def resolve_fakeids(session, timeout):
    fakeid = getattr(config, "WECHAT_FAKEID", "").strip()
    if fakeid:
        return [{"keyword": "configured", "fakeid": fakeid}]

    keywords = get_wechat_account_keywords()
    if not keywords:
        raise ValueError("请设置 WECHAT_FAKEID 或 WECHAT_ACCOUNT_KEYWORDS")

    resolved = []
    for keyword in keywords:
        print(f"正在检索公众号账号：{keyword}")
        payload = _api_get_json(
            session,
            "/account",
            {
                "keyword": keyword,
                "size": getattr(config, "WECHAT_ACCOUNT_SEARCH_SIZE", 1),
            },
            timeout,
        )
        candidates = _find_first_list(payload)
        if not candidates:
            continue
        account = candidates[0]
        found_fakeid = _first_value(account, "fakeid", "id", "biz", "__biz")
        if found_fakeid:
            print(f"已匹配公众号账号：{keyword}")
            resolved.append({"keyword": keyword, "fakeid": str(found_fakeid).strip()})

    if not resolved:
        raise RuntimeError("未找到任何可用公众号 fakeid")
    return resolved


def resolve_fakeid(session, timeout):
    resolved = resolve_fakeids(session, timeout)
    return resolved[0]["fakeid"]


def _normalize_article_item(raw, account_keyword=""):
    title = _first_value(raw, "title", "name") or "N/A"
    url = normalize_url(_first_value(raw, "url", "link", "content_url"))
    digest = _first_value(raw, "digest", "summary", "desc", "brief") or ""
    cover = normalize_url(_first_value(raw, "cover", "thumb_url", "image"))
    ts = parse_timestamp(_first_value(raw, "create_time", "datetime", "timestamp", "publish_time", "update_time"))

    aid = _first_value(raw, "aid")
    mid = _first_value(raw, "mid", "appmsgid")
    idx = _first_value(raw, "idx", "itemidx")
    if (not mid or not idx) and isinstance(aid, str) and "_" in aid:
        parts = aid.split("_", 1)
        if not mid and parts[0]:
            mid = parts[0]
        if not idx and len(parts) > 1 and parts[1]:
            idx = parts[1]

    return {
        "title": str(title),
        "url": url,
        "digest": str(digest),
        "cover": cover,
        "timestamp": ts,
        "aid": aid,
        "mid": str(mid) if mid is not None else None,
        "idx": str(idx) if idx is not None else None,
        "account_keyword": account_keyword,
    }


def fetch_articles(session, fakeid, timeout, account_keyword=""):
    label = account_keyword or fakeid
    print(f"正在读取公众号推送列表：{label}")
    payload = _api_get_json(
        session,
        "/article",
        {
            "fakeid": fakeid,
            "size": getattr(config, "WECHAT_ARTICLE_SIZE", 20),
        },
        timeout,
    )

    records = _find_first_list(payload)
    items = []
    for record in records:
        item = _normalize_article_item(record, account_keyword=account_keyword)
        if item.get("url"):
            items.append(item)
    print(f"公众号推送列表读取完成：{label}，共 {len(items)} 条")
    return items


def fetch_article_html(session, article_url, timeout):
    base_url = getattr(config, "WECHAT_PUBLIC_API_BASE_URL", "").strip().rstrip("/")
    encoded_url = quote(article_url, safe=":/?&=%#")
    fmt = quote(getattr(config, "WECHAT_DOWNLOAD_FORMAT", "html"), safe="")
    download_url = f"{base_url}/download?url={encoded_url}&format={fmt}"
    headers = {"X-Auth-Key": session.headers.get("X-Auth-Key", "")}
    resp = requests.request("GET", download_url, headers=headers, data={}, timeout=timeout)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "").lower()
    if "text/html" in content_type:
        return resp.text
    try:
        payload = resp.json()
    except ValueError:
        return resp.text
    return _find_html_in_obj(payload) or resp.text


def _find_html_in_obj(obj):
    if isinstance(obj, str):
        text = obj.strip()
        if "<" in text and ">" in text:
            return text
        return ""
    if isinstance(obj, dict):
        for key in ("html", "content", "data", "result", "body", "text"):
            if key in obj:
                result = _find_html_in_obj(obj[key])
                if result:
                    return result
        for value in obj.values():
            result = _find_html_in_obj(value)
            if result:
                return result
    if isinstance(obj, list):
        for value in obj:
            result = _find_html_in_obj(value)
            if result:
                return result
    return ""


def dedupe_items(items):
    seen = set()
    unique = []
    for item in items:
        mid = item.get("mid")
        idx = item.get("idx")
        if mid and idx:
            key = f"{mid}:{idx}"
        else:
            key = canonicalize_url_for_dedupe(item.get("url", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
