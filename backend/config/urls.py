from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .health import health

urlpatterns = [
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.students.urls")),
    path("api/", include("apps.staff.urls")),
    path("api/", include("apps.finance.urls")),
    path("api/", include("apps.reports.urls")),
    path("api/", include("apps.notifications.urls")),
    path("api/", include("apps.payments.urls")),
    path("api/", include("apps.academics.urls")),
    path("api/", include("apps.attendance.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
