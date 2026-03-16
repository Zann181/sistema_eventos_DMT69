from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from shared_ui import views as shared_ui_views


urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "login/",
        shared_ui_views.BrandedLoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("logout/", shared_ui_views.custom_logout, name="logout"),
    path("", include("shared_ui.urls")),
    path("sucursales/", include("branches.urls")),
    path("eventos/", include("events.urls")),
    path("entrada/", include("attendees.urls")),
    path("catalogo/", include("catalog.urls")),
    path("barra/", include("sales.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
