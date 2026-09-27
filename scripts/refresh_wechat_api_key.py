"""续期公众号 API 密钥（down.mptext.top）。

该站点的密钥与登录会话绑定：扫码登录后自动生成，有效期 4 天；登录失效密钥同时失效。
症状是 `GET /api/public/v1/authkey` 返回 `{"code":-1,"msg":"AuthKey not found"}`，
`/api/public/v1/account` 返回 `{"base_resp":{"ret":-1,"err_msg":"认证信息无效"}}` ——
接口没下线，只是密钥过期了。

本脚本用持久化 profile 打开站点，等用户扫码登录，然后用页面自己的会话去取新密钥，
校验可用后写回 `.env` 和用户级环境变量 `WECHAT_PUBLIC_API_KEY`。

    python scripts/refresh_wechat_api_key.py
    python scripts/refresh_wechat_api_key.py --profile-dir output/selenium_cache/mptext-profile
"""

import argparse
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

import config  # noqa: E402
from wanyou import browser as browser_module  # noqa: E402

SITE_URL = "https://down.mptext.top/"
DEFAULT_PROFILE_DIR = ROOT / "output" / "selenium_cache" / "mptext-profile"
DEFAULT_WAIT_SECONDS = 600
POLL_SECONDS = 3
PROGRESS_LOG_SECONDS = 30

# 在页面里用站点自己的会话取密钥：密钥与本网站登录集成，用页面内 fetch 才能带上 cookie。
FETCH_AUTHKEY_JS = """
const done = arguments[arguments.length - 1];
fetch('/api/public/v1/authkey', { credentials: 'include' })
  .then(r => r.json())
  .then(j => done(j))
  .catch(e => done({ code: -99, msg: String(e) }));
"""


def _key_env_name() -> str:
    return getattr(config, "WECHAT_PUBLIC_API_KEY_ENV", "WECHAT_PUBLIC_API_KEY")


def _base_url() -> str:
    return getattr(config, "WECHAT_PUBLIC_API_BASE_URL", "").strip().rstrip("/")


def verify_key(key: str, keyword: str = "清华大学学生会") -> tuple[bool, str]:
    """用一次真实的查询请求判断密钥是否可用。"""
    base = _base_url()
    if not base or not key:
        return False, "缺少 base_url 或密钥"
    try:
        resp = requests.get(
            base + "/account",
            params={"keyword": keyword},
            headers={"X-Auth-Key": key},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # pragma: no cover - network diagnostics
        return False, f"{type(exc).__name__}: {str(exc)[:160]}"

    base_resp = data.get("base_resp") if isinstance(data, dict) else None
    ret = base_resp.get("ret") if isinstance(base_resp, dict) else None
    if ret == 0:
        accounts = data.get("list") or []
        return True, f"可用，命中 {len(accounts)} 个公众号"
    return False, f"ret={ret} err_msg={(base_resp or {}).get('err_msg')}"


def write_env_file(key: str) -> pathlib.Path:
    """把密钥写回项目根的 .env，保留其余行。"""
    env_path = ROOT / ".env"
    name = _key_env_name()
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    replaced = False
    for index, line in enumerate(lines):
        if line.strip().startswith(name + "="):
            lines[index] = f"{name}={key}"
            replaced = True
            break
    if not replaced:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{name}={key}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env_path


def write_user_env(key: str) -> bool:
    """同步更新 Windows 用户级环境变量。

    `wechat_client._api_get_json` 在认证失败时会拿用户级变量重试一次。
    两处不同步的话，那个重试会继续拿旧密钥打一次，把日志搅浑。
    """
    if not sys.platform.startswith("win"):
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as handle:
            winreg.SetValueEx(handle, _key_env_name(), 0, winreg.REG_SZ, key)
        return True
    except OSError as exc:
        print(f"写入用户级环境变量失败（不影响 .env）：{exc}")
        return False


def fetch_authkey(browser) -> dict:
    try:
        result = browser.execute_async_script(FETCH_AUTHKEY_JS)
    except Exception as exc:
        return {"code": -98, "msg": f"{type(exc).__name__}: {str(exc)[:120]}"}
    return result if isinstance(result, dict) else {"code": -97, "msg": "返回体不是对象"}


def wait_for_login(browser, timeout: int) -> str:
    print("公众号密钥：浏览器已打开，请用微信扫码登录（登录后会自动继续，无需回车）。")
    deadline = time.time() + timeout
    next_log = time.time() + PROGRESS_LOG_SECONDS
    last_msg = ""
    while time.time() < deadline:
        payload = fetch_authkey(browser)
        code = payload.get("code")
        if code == 0:
            key = str(payload.get("data") or "").strip()
            if key:
                return key
            last_msg = "authkey 返回 code=0 但没有 data"
        elif code not in (-1, -99):
            last_msg = f"code={code} msg={payload.get('msg')}"

        if time.time() >= next_log:
            print(f"公众号密钥：仍在等待扫码（{last_msg or '未登录'}）")
            next_log = time.time() + PROGRESS_LOG_SECONDS
        time.sleep(POLL_SECONDS)

    raise RuntimeError(f"扫码登录超时（{timeout}s），最后状态：{last_msg or '未登录'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="续期公众号 API 密钥")
    parser.add_argument("--profile-dir", default=str(DEFAULT_PROFILE_DIR), help="持久化浏览器 profile 目录")
    parser.add_argument("--wait-seconds", type=int, default=DEFAULT_WAIT_SECONDS, help="等待扫码的秒数")
    parser.add_argument("--force", action="store_true", help="即使当前密钥仍可用也重新取一次")
    parser.add_argument("--keep-open", action="store_true", help="写完密钥后停在终端等回车，不立刻关浏览器")
    args = parser.parse_args()

    name = _key_env_name()
    current = os.environ.get(name, "").strip()
    print(f"公众号密钥：当前 .env 中的密钥长度 {len(current)}")

    if current and not args.force:
        ok, message = verify_key(current)
        print(f"公众号密钥：现有密钥自检 → {message}")
        if ok:
            print("公众号密钥：无需续期。要强制重取加 --force。")
            return 0

    profile_dir = pathlib.Path(args.profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)

    browser_name = browser_module.get_selenium_browser_name()
    options = browser_module.make_browser_options(browser_name, str(profile_dir))
    browser = browser_module.make_webdriver(browser_name, options)
    browser.set_script_timeout(30)
    try:
        browser.get(SITE_URL)
        key = wait_for_login(browser, args.wait_seconds)
        print(f"公众号密钥：已取到新密钥（长度 {len(key)}）")

        ok, message = verify_key(key)
        if not ok:
            print(f"公众号密钥：新密钥自检未通过 → {message}")
            return 1
        print(f"公众号密钥：新密钥自检通过 → {message}")

        env_path = write_env_file(key)
        print(f"公众号密钥：已写入 {env_path}")
        os.environ[name] = key
        if write_user_env(key):
            print(f"公众号密钥：已同步用户级环境变量 {name}")

        if args.keep_open:
            print("浏览器保持打开；在终端按回车结束。")
            try:
                input()
            except (EOFError, OSError):
                pass
        return 0
    finally:
        try:
            browser.quit()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
