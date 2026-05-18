from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))

SECRET_KEY = env("SECRET_KEY", default="change-me")
DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env(
    "DJANGO_ALLOWED_HOSTS", default="localhost 127.0.0.1 [::1]"
).split(" ")
DOMAIN = env("DOMAIN", default="localhost")
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", default="http://localhost:8000")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "api",
    "apps.clinic",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST"),
        "PORT": env("POSTGRES_PORT"),
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "ru"
TIME_ZONE = "Asia/Bishkek"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"

STATICFILES_DIRS = []

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS
CORS_ALLOW_ALL_ORIGINS = env.bool("CORS_ALLOW_ALL_ORIGINS", default=True)
CORS_ALLOW_CREDENTIALS = env.bool("CORS_ALLOW_CREDENTIALS", default=True)

# Build CSRF trusted origins from domain + all allowed hosts (so admin works by IP too)
_trusted = {f"http://{DOMAIN}", f"https://{DOMAIN}"}
for _h in ALLOWED_HOSTS:
    if _h not in ("*", ""):
        _trusted.add(f"http://{_h}")
        _trusted.add(f"https://{_h}")
CSRF_TRUSTED_ORIGINS = list(_trusted)

# DRF
REST_FRAMEWORK = {
    # По умолчанию делаем public API без авторизации.
    # Для защищённых эндпоинтов явно задаём authentication_classes в views.
    "DEFAULT_AUTHENTICATION_CLASSES": (),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.AllowAny",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "MamaDoc Booking API",
    "DESCRIPTION": "Backend API (Django + DRF)",
    "VERSION": "v1",
}

SIMPLE_JWT = {
    "SIGNING_KEY": env("JWT_SIGNING_KEY", default=SECRET_KEY),
}

AUTH_USER_MODEL = "auth.User"


# OTP dev bypass
DEV_OTP_BYPASS = env.bool("DEV_OTP_BYPASS", default=False)
DEV_OTP_PHONE = env("DEV_OTP_PHONE", default="+996700000000")
DEV_OTP_CODE = env("DEV_OTP_CODE", default="123456")

# SMS settings
SMS_LOGIN = env("SMS_LOGIN", default="")
SMS_PASSWORD = env("SMS_PASSWORD", default="")
SMS_SENDER = env("SMS_SENDER", default="")
SMS_API_URL = env("SMS_API_URL", default="https://smspro.nikita.kg/api/message")
