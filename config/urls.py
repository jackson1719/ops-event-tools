from django.contrib import admin
from django.urls import include, path

from events.views.media import serve_media

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("media/<path:path>", serve_media, name="media"),
    path("", include("events.urls")),
]
