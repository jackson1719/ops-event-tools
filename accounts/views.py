from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_not_required
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .themes import THEMES

LOGIN_MAX_ATTEMPTS = 10
LOGIN_LOCKOUT_SECONDS = 15 * 60


def _client_ip(request):
    """Real client IP behind the Cloudflare tunnel (falls back to REMOTE_ADDR)."""
    return (
        request.headers.get("CF-Connecting-IP")
        or request.META.get("REMOTE_ADDR", "?")
    )


def _throttle_key(request, username):
    return f"login-fail:{_client_ip(request)}:{username.lower()}"


@login_not_required
def login_view(request):
    if request.user.is_authenticated:
        return redirect("events:picker")

    if request.method == "POST":
        username = request.POST.get("username", "")
        key = _throttle_key(request, username)
        if cache.get(key, 0) >= LOGIN_MAX_ATTEMPTS:
            messages.error(request, "Too many failed attempts. Try again in a few minutes.")
        else:
            user = authenticate(
                request,
                username=username,
                password=request.POST.get("password", ""),
            )
            if user is not None:
                cache.delete(key)
                login(request, user)
                if request.POST.get("keep_signed_in"):
                    request.session.set_expiry(settings.KIOSK_SESSION_AGE)
                next_url = request.POST.get("next") or request.GET.get("next") or ""
                if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                    return redirect(next_url)
                return redirect("events:picker")
            cache.set(key, cache.get(key, 0) + 1, LOGIN_LOCKOUT_SECONDS)
            messages.error(request, "Invalid username or password.")

    from .models import SiteConfig
    cfg = SiteConfig.load()
    return render(request, "accounts/login.html", {
        "next": request.GET.get("next", ""),
        "show_google": cfg.google_ready,
        "show_code_login": cfg.code_login_enabled,
    })


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, "Logged out.")
    return redirect("accounts:login")


@require_POST
def set_theme(request):
    theme = request.POST.get("theme", "")
    if theme in THEMES:
        request.user.theme = theme
        request.user.save(update_fields=["theme"])
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("events:picker")
