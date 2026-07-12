"""Site Settings (Admin): auth methods, email, backups, users, events."""
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from events.audit import audit
from sync.backups import last_backup_time

from .forms import SiteConfigForm
from .models import SiteConfig
from .roles import ADMIN, require_role


@require_role(ADMIN)
def site_settings(request):
    cfg = SiteConfig.load()
    if request.method == "POST":
        form = SiteConfigForm(request.POST, instance=cfg)
        if form.is_valid():
            form.save()
            audit(None, request.user, "settings", "Site settings updated")
            messages.success(request, "Site settings saved — changes apply immediately.")
            return redirect("accounts:site_settings")
    else:
        form = SiteConfigForm(instance=cfg)

    return render(request, "accounts/site_settings.html", {
        "form": form,
        "cfg": cfg,
        "last_backup": last_backup_time(),
    })


@require_role(ADMIN)
@require_POST
def send_test_email(request):
    cfg = SiteConfig.load()
    to = request.user.email or cfg.from_email
    try:
        send_mail(
            "Ops Event Tools — test email",
            "SMTP is configured correctly.",
            cfg.from_email,
            [to],
        )
        if cfg.smtp_configured:
            messages.success(request, f"Test email sent to {to}.")
        else:
            messages.info(request, "SMTP not configured — test message printed to server logs.")
    except Exception as exc:
        messages.error(request, f"Send failed: {exc}")
    return redirect("accounts:site_settings")


@require_role(ADMIN)
@require_POST
def trigger_backup(request):
    import os
    from sync.backups import perform_backup

    try:
        path = perform_backup()
        audit(None, request.user, "backup", f"Manual backup: {os.path.basename(path)}")
        messages.success(request, f"Backup written: {os.path.basename(path)}")
    except Exception as exc:
        messages.error(request, f"Backup failed: {exc}")
    return redirect("accounts:site_settings")