import config
import sys
from wanyou.wechat_pipeline import run_wechat_public_output


def main():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    output_path, _items = run_wechat_public_output(
        days_limit=getattr(config, "WECHAT_DAYS_LIMIT", 0) or None
    )
    print(f"文件已保存至：{output_path}")


if __name__ == "__main__":
    main()
