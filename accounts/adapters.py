"""Closed-signup adapters + SiteConfig-driven provider/email configuration.

Signup is closed: accounts exist only when an Admin creates them. Google and
email-code logins authenticate EXISTING users matched by email. Google OAuth
credentials and the From address come from SiteConfig so they're editable in
Site Settings without a restart.
"""
from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialApp


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False

    def get_from_email(self):
        from .models import SiteConfig
        return SiteConfig.load().from_email


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        return False

    def list_apps(self, request, provider=None, client_id=None):
        """Source the Google app from SiteConfig instead of settings/DB."""
        from .models import SiteConfig
        cfg = SiteConfig.load()
        apps = []
        if cfg.google_ready and provider in (None, "google"):
            app = SocialApp(
                provider="google",
                name="Google",
                client_id=cfg.google_client_id,
                secret=cfg.google_client_secret,
            )
            if client_id is None or app.client_id == client_id:
                apps.append(app)
        return apps
