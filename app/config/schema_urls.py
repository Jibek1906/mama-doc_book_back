"""URLConf used only for OpenAPI schema generation.

Project exposes API under 2 prefixes for compatibility:
- /api/v1/*
- /v1/*

To avoid duplicated endpoints in Swagger UI, schema generation uses this URLConf
which includes only the canonical prefix (/v1) from BACKEND_SPEC.
"""

from django.urls import include, path


urlpatterns = [
    path("v1/", include("api.v1.urls")),
]
