"""Email backend that reads SMTP settings from SiteConfig at send time, so
Site Settings changes apply without a restart. Falls back to console output
(codes in server logs) when no SMTP user is configured.

Note: Django's test runner overrides EMAIL_BACKEND to locmem, so tests are
unaffected by this backend.
"""
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.console import EmailBackend as ConsoleBackend
from django.core.mail.backends.smtp import EmailBackend as SmtpBackend


class DynamicEmailBackend(BaseEmailBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._kwargs = kwargs

    def _delegate(self):
        from .models import SiteConfig
        cfg = SiteConfig.load()
        if cfg.smtp_configured:
            return SmtpBackend(
                host=cfg.email_host,
                port=cfg.email_port,
                username=cfg.email_host_user,
                password=cfg.email_host_password,
                use_tls=cfg.email_use_tls,
                fail_silently=self.fail_silently,
            )
        return ConsoleBackend(fail_silently=self.fail_silently, **self._kwargs)

    def send_messages(self, email_messages):
        return self._delegate().send_messages(email_messages)
