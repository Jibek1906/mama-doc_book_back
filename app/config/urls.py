from django.contrib import admin
from django.http import HttpResponseNotFound
from django.urls import include, path

from django.conf import settings
from django.conf.urls.static import static

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularJSONAPIView,
    SpectacularSwaggerView,
)


# Эти endpoints нужны чтобы Swagger UI мог загрузить схему,
# но в самой схеме (и в списке ручек Swagger UI) они не должны отображаться.
class HiddenSpectacularAPIView(SpectacularAPIView):
    schema = None


class HiddenSpectacularJSONAPIView(SpectacularJSONAPIView):
    schema = None

from django.views.generic import TemplateView

from django.views.decorators.csrf import csrf_exempt

from api.graphql_schema import schema as graphql_schema
from api.graphql_view import MamaDocGraphQLView

urlpatterns = [
    # Legacy admin URLs must not exist anymore
    path("admin/clinic/", lambda request: HttpResponseNotFound("Not Found")),
    path("admin/clinic/<path:path>", lambda request, path: HttpResponseNotFound("Not Found")),
    path("admin/", admin.site.urls),
    # PRO UI
    # canonical: /pro/ (requested), keep /pro-cabinet/ for backward compatibility
    path("pro/", TemplateView.as_view(template_name="pro_cabinet.html"), name="pro"),
    path("pro-cabinet/", TemplateView.as_view(template_name="pro_cabinet.html"), name="pro-cabinet"),
    path("api/", include("api.urls")),
    # Spec-compatible base path: /v1/* (same as /api/v1/*)
    # Enabled by default so frontend/integrations can safely use either prefix.
    path("v1/", include("api.v1.urls")),
    # schema: оставляем YAML по умолчанию + добавляем JSON для Swagger UI
    path("api/schema/", HiddenSpectacularAPIView.as_view(), name="schema"),
    path("api/schema.json", HiddenSpectacularJSONAPIView.as_view(), name="schema-json"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema-json"),
        name="swagger-ui",
    ),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(url_name="schema-json"),
        name="swagger-ui-alias",
    ),

    # GraphQL endpoint (new, REST remains unchanged)
    path(
        "graphql/",
        csrf_exempt(
            MamaDocGraphQLView.as_view(
                schema=graphql_schema,
                graphql_ide="graphiql" if settings.DEBUG else None,
            )
        ),
        name="graphql",
    ),
]


# В DEV нужно уметь отдавать статические файлы (иконки/фото),
# т.к. фронт использует `icon_url`/`photo_url`.
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
