from getpass import getpass


def prompt_credentials():
    username = input("请输入登录用户名: ").strip()
    password = getpass("请输入登录密码: ").strip()
    return username, password
