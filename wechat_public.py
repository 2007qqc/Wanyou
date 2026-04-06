import config
from wanyou.wechat_pipeline import run_wechat_public_output


def main():
    output_path, _items = run_wechat_public_output(
        days_limit=getattr(config, "WECHAT_DAYS_LIMIT", 0) or None
    )
    print(f"文件已保存至：{output_path}")


if __name__ == "__main__":
    main()
