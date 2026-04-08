import sys

try:
    import msvcrt
except Exception:
    msvcrt = None

from getpass import getpass


def _masked_password_prompt(prompt_text):
    if msvcrt is None or not sys.stdin.isatty():
        return getpass(prompt_text)

    sys.stdout.write(prompt_text)
    sys.stdout.flush()
    chars = []
    while True:
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            sys.stdout.write("\n")
            sys.stdout.flush()
            return "".join(chars)
        if ch == "\003":
            raise KeyboardInterrupt
        if ch == "\b":
            if chars:
                chars.pop()
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            continue
        if ch in ("\x00", "\xe0"):
            try:
                msvcrt.getwch()
            except Exception:
                pass
            continue
        chars.append(ch)
        sys.stdout.write("\u00b7")
        sys.stdout.flush()


def prompt_credentials():
    print("\n[统一身份认证] 教务通知和家园网默认复用同一套清华账号")
    username = input("用户名: ").strip()
    password = _masked_password_prompt("密码: ").strip()
    return {
        "info": {"username": username, "password": password},
        "myhome": {"username": username, "password": password},
    }
