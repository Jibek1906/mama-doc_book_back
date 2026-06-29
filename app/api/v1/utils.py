import random
import re
from datetime import date, datetime, time, timedelta
from urllib.parse import urlparse, urlunparse

from django.conf import settings
from django.utils import timezone
from rest_framework.views import exception_handler


INTERNAL_MEDIA_HOSTS = {"backend:8000", "localhost:8000", "127.0.0.1:8000"}


def api_error(*, error: str, message: str, details=None):
    return {"error": error, "message": message, "details": details or {}}


def public_absolute_url(path: str) -> str:
    """Build a browser-accessible absolute URL for API media/static fields."""

    if not path:
        return ""

    raw = str(path).strip()
    parsed = urlparse(raw)

    if parsed.scheme in {"http", "https"}:
        if parsed.netloc not in INTERNAL_MEDIA_HOSTS:
            return raw
        raw = urlunparse(("", "", parsed.path, "", parsed.query, parsed.fragment))

    public_base_url = str(getattr(settings, "PUBLIC_BASE_URL", "")).rstrip("/")
    if not public_base_url:
        return raw

    if raw.startswith("/"):
        return f"{public_base_url}{raw}"
    return f"{public_base_url}/{raw}"


def drf_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return response

    if isinstance(response.data, dict):
        details = response.data
    else:
        details = {"errors": response.data}

    status = getattr(response, "status_code", 500)
    if status == 400:
        error = "validation_error"
        message = "Невалидные данные"
    elif status == 409:
        error = "conflict"
        message = "Конфликт"
    elif status == 429:
        error = "too_many_requests"
        message = "Слишком много запросов"
    elif status == 401:
        error = "not_authenticated"
        message = "Не авторизован"
    elif status == 403:
        error = "forbidden"
        message = "Нет доступа"
    elif status == 404:
        error = "not_found"
        message = "Не найдено"
    else:
        error = "server_error"
        message = "Ошибка сервера"

    response.data = api_error(error=error, message=message, details=details)
    return response


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


def normalize_phone(raw_phone: str) -> str:
    """Normalize phone into E.164-like format used by the project.

    Accepted inputs examples:
    - "+996700123456"
    - "996700123456" (missing '+')
    - "0700123456" (KG local with leading 0) -> "+996700123456"
    - "700123456" (KG local without 0) -> "+996700123456"
    - "+7 777 123 45 67" (spaces)
    - "87771234567" (RU/KZ '8' prefix) -> "+77771234567"
    """

    if not raw_phone:
        return ""

    s = str(raw_phone).strip()
    # keep only digits; handle leading '+' separately
    digits = re.sub(r"\D", "", s)

    # handle international prefix like 00...
    if digits.startswith("00"):
        digits = digits[2:]

    # RU/KZ local prefix 8XXXXXXXXXX -> +7XXXXXXXXXX
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]

    # KG local formats:
    # - 0XXXXXXXXX (10 digits) -> 996XXXXXXXXX
    # - XXXXXXXXX (9 digits)   -> 996XXXXXXXXX
    # Note: We keep this intentionally simple for frontend convenience.
    if digits.startswith("0") and len(digits) == 10:
        digits = "996" + digits[1:]
    elif len(digits) == 9 and digits.startswith(("5", "6", "7")):
        digits = "996" + digits

    # If number looks like it already contains the country code but lacks '+', add it.
    if digits.startswith("996") and len(digits) == 12:
        return f"+{digits}"
    if digits.startswith("7") and len(digits) == 11:
        return f"+{digits}"

    # If user already passed '+', they likely intended E.164
    if s.startswith("+") and digits:
        return f"+{digits}"

    # fallback: return as-is (will be rejected by validation later)
    return s


def is_supported_phone(phone: str) -> bool:
    """Project rule: only +996XXXXXXXXX (13 chars) and +7XXXXXXXXXX (12 chars)."""

    if not phone:
        return False
    if phone.startswith("+996") and len(phone) == 13:
        return True
    if phone.startswith("+7") and len(phone) == 12:
        return True
    return False
