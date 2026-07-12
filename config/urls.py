from django.contrib import admin
from django.contrib.auth.decorators import login_not_required
from django.urls import include, path
from django.views.generic import TemplateView

from accounts.views_acme import acme_challenge
from events.views.media import serve_media

# Served at the root so its scope covers the whole site
service_worker = login_not_required(
    TemplateView.as_view(template_name="sw.js", content_type="application/javascript")
)

urlpatterns = [
    path("admin/", admin.site.urls),
    # Our accounts routes first: login/logout/theme/users shadow allauth's
    # equivalents; allauth supplies Google OAuth + email-code flows.
    path("accounts/", include("accounts.urls")),
    path("accounts/", include("allauth.urls")),
    path("media/<path:path>", serve_media, name="media"),
    path("sw.js", service_worker, name="service_worker"),
    path(".well-known/acme-challenge/<str:token>", acme_challenge, name="acme_challenge"),
    path("", include("events.urls")),
]
