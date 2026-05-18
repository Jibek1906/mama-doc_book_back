import random
from datetime import date, datetime, time, timedelta

from django.utils import timezone


def api_error(*, error: str, message: str, details=None):
    return {"error": error, "message": message, "details": details or {}}


def make_confirmation_code(prefix: str = "TG") -> str:
    return f"{prefix}{random.randint(10000, 99999)}"


def bishek_now():
    return timezone.localtime(timezone.now())


def label_for_day(target_date: date) -> str:
    today = bishek_now().date()
    if target_date == today:
        return "Сегодня"
    if target_date == today + timedelta(days=1):
        return "Завтра"

    months = [
        "янв",
        "фев",
        "мар",
        "апр",
        "мая",
        "июн",
        "июл",
        "авг",
        "сен",
        "окт",
        "ноя",
        "дек",
    ]
    return f"{target_date.day} {months[target_date.month - 1]}"


def time_range(start: time, end: time, step_min: int):
    cur = datetime.combine(date.today(), start)
    end_dt = datetime.combine(date.today(), end)
    while cur < end_dt:
        yield cur.time()
        cur += timedelta(minutes=step_min)
