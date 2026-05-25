from pathlib import Path
from datetime import timedelta

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))

SECRET_KEY = env("SECRET_KEY", default="change-me")
DEBUG = env.bool("DEBUG", default=False)

# NOTE:
# /v1/* compatibility routes are enabled unconditionally in config/urls.py
# to match backend spec and allow painless frontend integration.

ALLOWED_HOSTS = env(
    "DJANGO_ALLOWED_HOSTS", default="localhost 127.0.0.1 [::1]"
).split(" ")
DOMAIN = env("DOMAIN", default="localhost")
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", default="http://localhost:8000")

# Optional release marker (useful to verify prod deploy)
RELEASE = env("RELEASE", default="dev")

INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
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
    "apps.organizations.apps.OrganizationsConfig",
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

# If Django is behind a reverse proxy (nginx) terminating SSL, tell it to trust
# the forwarded proto so request.build_absolute_uri() uses https:// URLs.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Redirect all HTTP requests to HTTPS in production
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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
    "EXCEPTION_HANDLER": "api.v1.utils.drf_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "MamaDoc Booking API",
    "DESCRIPTION": "Backend API (Django + DRF)",
    "VERSION": "v1",
    # Make Swagger usable for JWT-protected endpoints.
    # After calling /auth/verify-otp, paste access_token into Authorize dialog:
    #   Bearer <token>
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
    },
    "COMPONENTS": {
        "securitySchemes": {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
        }
    },
    # Default security (public endpoints explicitly set auth=[] in @extend_schema)
    "SECURITY": [{"bearerAuth": []}],
    # Avoid duplicated operationId when both /api/v1/* and /v1/* are exposed.
    "CAMELIZE_NAMES": False,

    # Avoid duplicate endpoints in Swagger UI.
    # Project exposes API under both /api/v1/* and /v1/* for compatibility,
    # but the schema should contain only the canonical prefix (/v1).
    "SERVE_URLCONF": "config.schema_urls",
    "POSTPROCESSING_HOOKS": [
        "api.v1.schema_hooks.postprocess_schema",
    ],
}

JWT_EXPIRE_MINUTES = env.int("JWT_EXPIRE_MINUTES", default=10080)

SIMPLE_JWT = {
    "SIGNING_KEY": env("JWT_SIGNING_KEY", default=SECRET_KEY),
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=JWT_EXPIRE_MINUTES),
}

AUTH_USER_MODEL = "auth.User"


# OTP dev bypass
DEV_OTP_BYPASS = env.bool("DEV_OTP_BYPASS", default=False)
DEV_OTP_PHONE = env("DEV_OTP_PHONE", default="+996700000000")
DEV_OTP_CODE = env("DEV_OTP_CODE", default="123456")

# OTP rules
OTP_EXPIRE_SECONDS = env.int("OTP_EXPIRE_SECONDS", default=60)
OTP_MAX_ATTEMPTS = env.int("OTP_MAX_ATTEMPTS", default=5)
OTP_RESEND_COOLDOWN = env.int("OTP_RESEND_COOLDOWN", default=60)
OTP_MAX_SENDS_PER_HOUR = env.int("OTP_MAX_SENDS_PER_HOUR", default=3)
OTP_BLOCK_SECONDS = env.int("OTP_BLOCK_SECONDS", default=300)

# Elasticsearch (professional search)
ES_ENABLED = env.bool("ES_ENABLED", default=False)
ES_URL = env("ES_URL", default="http://elasticsearch:9200")
ES_DOCTORS_INDEX = env("ES_DOCTORS_INDEX", default="mamadoc_doctors")
ES_TIMEOUT_SECONDS = env.int("ES_TIMEOUT_SECONDS", default=2)

# SMS settings
SMS_LOGIN = env("SMS_LOGIN", default="")
SMS_PASSWORD = env("SMS_PASSWORD", default="")
SMS_SENDER = env("SMS_SENDER", default="")
SMS_API_URL = env("SMS_API_URL", default="https://smspro.nikita.kg/api/message")

# Unfold Admin UI Settings
UNFOLD = {
    "SITE_TITLE": "MamaDoc Admin",
    "SITE_HEADER": "MamaDoc Platform",
    "SITE_URL": "/",
    "SITE_SYMBOL": "medical_services",
    "DASHBOARD_CALLBACK": None,
    "COLORS": {
        "primary": {
            "50": "#f0fdf4",
            "100": "#dcfce7",
            "200": "#bbf7d0",
            "300": "#86efac",
            "400": "#4ade80",
            "500": "#22c55e",
            "600": "#16a34a",
            "700": "#15803d",
            "800": "#166534",
            "900": "#14532d",
            "950": "#052e16",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": "Проект",
                "separator": True,
                "items": [
                    {
                        "title": "Специалисты",
                        "icon": "medication",
                        "link": "/admin/organizations/professional/",
                    },
                    {
                        "title": "Услуги",
                        "icon": "design_services",
                        "link": "/admin/organizations/service/",
                    },
                    {
                        "title": "Организации",
                        "icon": "apartment",
                        "link": "/admin/organizations/organization/",
                    },
                    {
                        "title": "Филиалы",
                        "icon": "location_on",
                        "link": "/admin/organizations/branch/",
                    },
                    {
                        "title": "Специализации",
                        "icon": "psychology",
                        "link": "/admin/organizations/specialist/",
                    },
                    {
                        "title": "Настройки функций (Paylink и филиалы)",
                        "icon": "settings",
                        "link": "/admin/organizations/projectfeaturesettings/",
                    },
                    {
                        "title": "Записи (Bookings)",
                        "icon": "calendar_month",
                        "link": "/admin/organizations/booking/",
                    },
                    {
                        "title": "Отзывы",
                        "icon": "star",
                        "link": "/admin/organizations/review/",
                    },
                    {
                        "title": "Клиенты",
                        "icon": "patient_list",
                        "link": "/admin/organizations/client/",
                    },
                ],
            },
            {
                "title": "Авторизация и SMS",
                "separator": True,
                "items": [
                    {
                        "title": "OTP Коды",
                        "icon": "vpn_key",
                        "link": "/admin/organizations/otpcode/",
                    },
                    {
                        "title": "SMS Логи",
                        "icon": "sms",
                        "link": "/admin/organizations/smscode/",
                    },
                    {
                        "title": "Страны и коды",
                        "icon": "language",
                        "link": "/admin/organizations/phonecountry/",
                    },
                ],
            },
            {
                "title": "Система",
                "separator": True,
                "items": [
                    {
                        "title": "Пользователи",
                        "icon": "group",
                        "link": "/admin/auth/user/",
                    },
                    {
                        "title": "Swagger API",
                        "icon": "api",
                        "link": "/docs",
                    },
                ],
            },
        ],
    },
}
