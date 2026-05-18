from django.contrib import admin
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

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    # schema: оставляем YAML по умолчанию + добавляем JSON для Swagger UI
    path("api/schema/", HiddenSpectacularAPIView.as_view(), name="schema"),
    path("api/schema.json", HiddenSpectacularJSONAPIView.as_view(), name="schema-json"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema-json"),
        name="swagger-ui",
    ),
]


# В DEV нужно уметь отдавать статические файлы (иконки/фото),
# т.к. фронт использует `icon_url`/`photo_url`.
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
