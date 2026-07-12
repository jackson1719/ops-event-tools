import os
import secrets

from django.contrib.auth.models import AbstractUser
from django.db import models

from .themes import DEFAULT_THEME, THEME_CHOICES


class User(AbstractUser):
    staff_name = models.CharField(
        max_length=200, blank=True,
        help_text="Name exactly as it appears in the Staff Shifts sheet — links shifts to this account.",
    )
    ical_token = models.CharField(max_length=64, blank=True, editable=False)
    theme = models.CharField(max_length=20, choices=THEME_CHOICES, default=DEFAULT_THEME)

    def get_or_create_ical_token(self) -> str:
        if not self.ical_token:
            self.ical_token = secrets.token_urlsafe(32)
            self.save(update_fields=["ical_token"])
        return self.ical_token


class SiteConfig(models.Model):
    """Singleton site-wide configuration, editable in Site Settings.

    Seeded from environment variables on first load so existing .env-based
    deployments migrate transparently; the DB is authoritative afterwards.
    Secrets (SMTP password, OAuth secret) live here by explicit choice —
    same box and same backups as everything else in this internal tool.
    """

    # Authentication methods (local username/password is always available)
    google_login_enabled = models.BooleanField(default=False)
    google_client_id = models.CharField(max_length=200, blank=True)
    google_client_secret = models.CharField(max_length=200, blank=True)
    code_login_enabled = models.BooleanField(
        default=True, help_text="Emailed one-time sign-in codes (requires SMTP below).")

    # Outgoing email (sign-in codes). Blank username = codes print to server logs.
    email_host = models.CharField(max_length=200, blank=True, default="smtp.gmail.com")
    email_port = models.PositiveIntegerField(default=587)
    email_use_tls = models.BooleanField(default=True)
    email_host_user = models.CharField(max_length=200, blank=True)
    email_host_password = models.CharField(max_length=200, blank=True)
    default_from_email = models.CharField(max_length=200, blank=True)

    # Backups (BACKUP_DIR stays an environment concern — it's a filesystem path)
    backup_enabled = models.BooleanField(default=True)
    backup_interval_hours = models.PositiveIntegerField(default=24)
    backup_keep = models.PositiveIntegerField(default=14)

    class Meta:
        verbose_name = "site configuration"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "SiteConfig":
        obj, _ = cls.objects.get_or_create(pk=1, defaults={
            "google_client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
            "google_client_secret": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "google_login_enabled": bool(os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")),
            "email_host": os.getenv("EMAIL_HOST", "smtp.gmail.com"),
            "email_port": int(os.getenv("EMAIL_PORT", "587")),
            "email_host_user": os.getenv("EMAIL_HOST_USER", ""),
            "email_host_password": os.getenv("EMAIL_HOST_PASSWORD", ""),
            "default_from_email": os.getenv("DEFAULT_FROM_EMAIL", ""),
            "backup_enabled": os.getenv("BACKUP_ENABLED", "true").lower() in ("1", "true", "yes"),
            "backup_interval_hours": int(os.getenv("BACKUP_INTERVAL_HOURS", "24")),
            "backup_keep": int(os.getenv("BACKUP_KEEP", "14")),
        })
        return obj

    @property
    def google_ready(self) -> bool:
        return self.google_login_enabled and bool(self.google_client_id and self.google_client_secret)

    @property
    def smtp_configured(self) -> bool:
        return bool(self.email_host_user)

    @property
    def from_email(self) -> str:
        return self.default_from_email or self.email_host_user or "ops-event-tools@localhost"
