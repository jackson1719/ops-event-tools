import secrets

from django.conf import settings
from django.contrib.auth.middleware import LoginRequiredMiddleware as DjangoLoginRequiredMiddleware


class ContentSecurityPolicyMiddleware:
    """Nonce-based CSP.

    script-src uses a per-request nonce + 'strict-dynamic': injected inline
    scripts and on*= handlers are blocked, while our own nonce'd scripts (and
    anything they load — HTMX swaps, the fetch-and-re-run-scripts pattern, the
    CDN bundles) stay trusted. style-src keeps 'unsafe-inline' because inline
    style="" attributes are pervasive and script is the real XSS vector.

    The Django admin (superuser-only, ships its own unnonced inline JS) is
    exempted.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(16)
        response = self.get_response(request)
        if request.path.startswith("/admin/") or "Content-Security-Policy" in response:
            return response
        nonce = request.csp_nonce
        response["Content-Security-Policy"] = "; ".join([
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}' 'strict-dynamic' https:",
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            "img-src 'self' data:",
            "font-src 'self'",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "frame-ancestors 'none'",
            "form-action 'self'",
        ])
        return response



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
            # Code login can be switched off in Site Settings
            if request.path.startswith("/accounts/login/code"):
                from .models import SiteConfig
                if not SiteConfig.load().code_login_enabled:
                    from django.shortcuts import redirect
                    return redirect(settings.LOGIN_URL)
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
