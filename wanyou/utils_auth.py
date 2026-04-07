from getpass import getpass


def prompt_credentials():
    print("\n[统一身份认证] 教务通知和家园网默认复用同一套清华账号")
    username = input("用户名: ").strip()
    password = getpass("密码: ").strip()
    return {
        "info": {"username": username, "password": password},
        "myhome": {"username": username, "password": password},
    }
