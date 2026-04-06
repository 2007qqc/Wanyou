import datetime
import time


def days_since_date(date_str, date_format="%Y-%m-%d"):
    date_struct = time.strptime(date_str, date_format)
    timestamp_date = time.mktime(date_struct)
    timestamp_now = time.time()
    diff_seconds = (timestamp_now - timestamp_date)
    diff_days = diff_seconds // 86400
    return diff_days


def is_after_next_monday(target_date) -> bool:
    today = datetime.datetime.today().date()
    current_weekday = today.weekday()
    days_until_next_monday = (0 - current_weekday) % 7
    return -(days_until_next_monday + 7) < days_since_date(target_date) < -days_until_next_monday
