"""日期/时间展示工具。"""

import datetime


def format_datetime_text(item):
    """把条目时间戳格式化成「YYYY-MM-DD HH:MM」；没有时间戳时退回发布时间文本。"""
    timestamp = item.get("timestamp")
    if timestamp:
        return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
    return (item.get("publish_time") or "").strip() or "N/A"
