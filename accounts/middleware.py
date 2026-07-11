from django.conf import settings
from django.contrib.auth.middleware import LoginRequiredMiddleware as DjangoLoginRequiredMiddleware


class LoginRequiredMiddleware(DjangoLoginRequiredMiddleware):
    """Site-wide login enforcement, with allauth's views exempted.

    Not every allauth view carries @login_not_required (RequestLoginCodeView
    doesn't, as of 65.18), and allauth guards its own authenticated views with
    @login_required — so exempting by module is safe. Our own views under
    accounts/ (e.g. /accounts/users/) are NOT in the allauth module and stay
    protected.
    """

    def process_view(self, request, view_func, view_args, view_kwargs):
        if (getattr(view_func, "__module__", "") or "").startswith("allauth."):
            return None
        return super().process_view(request, view_func, view_args, view_kwargs)


class HtmxLoginRedirectMiddleware:
    """When an HTMX partial request hits the login redirect, tell HTMX to do a
    full-page redirect instead of swapping the login page into a fragment."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            request.headers.get("HX-Request") == "true"
            and response.status_code == 302
            and response.get("Location", "").startswith(settings.LOGIN_URL)
        ):
            response.status_code = 401
            response["HX-Redirect"] = response["Location"]
        return response
