import hashlib
import json
import os

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

import config
from wanyou.utils_web import dump_browser_snapshot, make_browser


def _find_first(browser, selectors):
    for by, value in selectors:
        try:
            return browser.find_element(by, value)
        except Exception:
            continue
    raise NoSuchElementException(f"Unable to locate any selector from: {selectors}")


def _looks_like_login_page(browser):
    selectors = [
        (By.ID, "i_user"),
        (By.ID, "i_pass"),
        (By.NAME, "username"),
        (By.NAME, "password"),
        (By.CSS_SELECTOR, "input[type='password']"),
    ]
    for by, value in selectors:
        try:
            if browser.find_elements(by, value):
                return True
        except Exception:
            continue
    return False


def _get_login_error(browser):
    selectors = [
        (By.ID, "msg_note"),
        (By.CSS_SELECTOR, "#c_note #msg_note"),
        (By.CSS_SELECTOR, ".alert-danger"),
        (By.CSS_SELECTOR, ".red"),
    ]
    for by, value in selectors:
        try:
            elements = browser.find_elements(by, value)
        except Exception:
            continue
        for element in elements:
            text = (element.text or "").strip()
            if text:
                return text
    return ""


def _wait_for_auth_result(browser):
    def _auth_finished(driver):
        current_url = (driver.current_url or "").lower()
        if "id.tsinghua.edu.cn" not in current_url:
            return "success"
        error_text = _get_login_error(driver)
        if error_text:
            return "error"
        return False

    try:
        return WebDriverWait(browser, max(config.WAIT_TIMEOUT, 20)).until(_auth_finished)
    except Exception:
        return "timeout"


def _install_login_probe(browser):
    browser.execute_script(
        """
        window.__codex_login_marker = "CODEX_LOGIN_ATTEMPT::";
        var form = document.getElementById("theform") || document.querySelector("form");
        if (!form || form.__codexWrapped) {
            return;
        }
        var originalSubmit = form.submit.bind(form);
        form.submit = function() {
            var payload = {
                submitted_user: (document.getElementById("i_user") || {}).value || "",
                sm2pass_length: ((document.getElementById("sm2pass") || {}).value || "").length,
                finger_print_length: ((document.getElementById("fingerPrint") || {}).value || "").length,
                finger_gen_print_length: ((document.getElementById("fingerGenPrint") || {}).value || "").length,
                device_name: (document.getElementById("deviceName") || {}).value || "",
                captcha_visible: !!(document.getElementById("c_code") && !document.getElementById("c_code").classList.contains("hidden")),
            };
            try {
                window.name = window.__codex_login_marker + JSON.stringify(payload);
            } catch (e) {}
            return originalSubmit();
        };
        form.__codexWrapped = true;
        """
    )


def _read_login_probe(browser):
    try:
        raw = browser.execute_script("return window.name || '';")
    except Exception:
        return {}
    prefix = "CODEX_LOGIN_ATTEMPT::"
    if not raw or not str(raw).startswith(prefix):
        return {}
    try:
        return json.loads(str(raw)[len(prefix):])
    except Exception:
        return {}


def _write_login_attempt_summary(debug_dir, name, username, password, probe_data, auth_result, login_error):
    lines = [
        f"username: {username}",
        f"username_length: {len(username)}",
        f"password_length: {len(password)}",
        f"password_sha256: {hashlib.sha256(password.encode('utf-8')).hexdigest()}",
        f"auth_result: {auth_result}",
        f"login_error: {login_error}",
        f"probe_submitted_user: {probe_data.get('submitted_user', '')}",
        f"probe_sm2pass_length: {probe_data.get('sm2pass_length', 0)}",
        f"probe_finger_print_length: {probe_data.get('finger_print_length', 0)}",
        f"probe_finger_gen_print_length: {probe_data.get('finger_gen_print_length', 0)}",
        f"probe_device_name: {probe_data.get('device_name', '')}",
        f"probe_captcha_visible: {probe_data.get('captcha_visible', False)}",
    ]
    os.makedirs(debug_dir, exist_ok=True)
    with open(os.path.join(debug_dir, f"{name}.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _trigger_encrypted_login(browser):
    script_calls = [
        "if (typeof doLogin === 'function') { doLogin(); return true; } return false;",
        "if (typeof login === 'function') { login(); return true; } return false;",
        "if (typeof submitForm === 'function') { submitForm(); return true; } return false;",
    ]
    for script in script_calls:
        try:
            if browser.execute_script(script):
                return
        except Exception:
            continue

    button_selectors = [
        (By.CSS_SELECTOR, "a.btn.btn-lg.btn-primary.btn-block"),
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.CSS_SELECTOR, "input[type='submit']"),
        (By.CSS_SELECTOR, "button.login"),
        (By.CSS_SELECTOR, "a.login"),
        (By.XPATH, "//button[contains(normalize-space(.), '登录')]"),
        (By.XPATH, "//a[contains(normalize-space(.), '登录')]"),
        (By.XPATH, "//input[@type='button' and contains(@value, '登录')]"),
        (By.XPATH, "//input[@type='submit' and contains(@value, '登录')]"),
    ]
    for by, value in button_selectors:
        try:
            button = browser.find_element(by, value)
            browser.execute_script("arguments[0].click();", button)
            return
        except Exception:
            continue

    form_selectors = [
        (By.ID, "theform"),
        (By.CSS_SELECTOR, "form"),
    ]
    for by, value in form_selectors:
        try:
            form = browser.find_element(by, value)
        except Exception:
            continue
        try:
            browser.execute_script("arguments[0].submit();", form)
            return
        except Exception:
            try:
                form.submit()
                return
            except Exception:
                continue

    raise NoSuchElementException("Unable to trigger login submit: no known login function, button, or form was usable")


def _build_auth_failure_message(browser, stage_label: str, login_error: str) -> str:
    current_url = (getattr(browser, "current_url", "") or "").lower()
    title = (getattr(browser, "title", "") or "").strip()
    if login_error:
        return f"{stage_label}登录未通过：{login_error}"
    if "/do/off/ui/auth/login/check" in current_url or "二次认证" in title:
        return f"{stage_label}已进入统一认证二次认证页面，当前程序尚不能自动完成该步骤"
    if "/f/login" in current_url or "登录" in title:
        return f"{stage_label}统一认证流程未完成，程序已填写用户名并尝试提交，但登录页未放行"
    return f"{stage_label}登录未通过，请检查统一认证流程或稍后重试"


def _fill_credentials_and_submit(browser, username: str, password: str):
    username_input = _find_first(
        browser,
        [(By.ID, "i_user"), (By.NAME, "username"), (By.CSS_SELECTOR, "input[type='text']")],
    )
    username_input.clear()
    username_input.send_keys(username)

    password_input = _find_first(
        browser,
        [(By.ID, "i_pass"), (By.NAME, "password"), (By.CSS_SELECTOR, "input[type='password']")],
    )
    password_input.clear()
    password_input.send_keys(password)

    _install_login_probe(browser)
    _trigger_encrypted_login(browser)


def authenticate_shared_browser(username: str, password: str, debug_dir: str, initial_url: str, stage_label: str = "统一认证"):
    browser = make_browser(headless=False)
    os.makedirs(debug_dir, exist_ok=True)

    print(f"正在打开{stage_label}浏览器会话")
    browser.get(initial_url)
    dump_browser_snapshot(browser, debug_dir, "shared_before_login")

    current_url = (browser.current_url or "").lower()
    if not _looks_like_login_page(browser) and "id.tsinghua.edu.cn" not in current_url:
        dump_browser_snapshot(browser, debug_dir, "shared_already_authenticated")
        print(f"{stage_label}检测到已有登录会话，直接复用")
        return browser

    print(f"正在提交{stage_label}账号密码")
    try:
        _fill_credentials_and_submit(browser, username, password)
    except Exception:
        dump_browser_snapshot(browser, debug_dir, "shared_submit_failed")
        raise

    auth_result = _wait_for_auth_result(browser)
    login_error = _get_login_error(browser)
    probe_data = _read_login_probe(browser)
    _write_login_attempt_summary(
        debug_dir,
        "shared_login_attempt",
        username,
        password,
        probe_data,
        auth_result,
        login_error,
    )
    dump_browser_snapshot(browser, debug_dir, "shared_after_login")

    if auth_result == "success" and not _looks_like_login_page(browser):
        print(f"{stage_label}登录成功")
        return browser

    print(_build_auth_failure_message(browser, stage_label, login_error))
    print("已打开可见 Edge 浏览器。你可以在该窗口中完成统一认证或二次认证。")
    input("确认浏览器中已经完成登录后，按回车继续...")

    try:
        browser.get(initial_url)
    except Exception:
        pass
    dump_browser_snapshot(browser, debug_dir, "shared_after_manual_auth")

    if _looks_like_login_page(browser) or "id.tsinghua.edu.cn" in (browser.current_url or "").lower():
        message = _build_auth_failure_message(browser, stage_label, _get_login_error(browser))
        browser.quit()
        raise RuntimeError(message)

    return browser
