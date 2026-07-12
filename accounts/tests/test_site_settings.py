from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase

from accounts.models import SiteConfig, User


class SiteSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for role in ["Manager", "Admin"]:
            u = User.objects.create_user(role.lower(), password="pw", email=f"{role.lower()}@example.com")
            u.groups.add(Group.objects.get(name=role))

    def test_admin_only(self):
        self.client.login(username="manager", password="pw")
        self.assertEqual(self.client.get("/accounts/site-settings/").status_code, 403)
        self.client.login(username="admin", password="pw")
        self.assertEqual(self.client.get("/accounts/site-settings/").status_code, 200)

    def test_save_config(self):
        self.client.login(username="admin", password="pw")
        resp = self.client.post("/accounts/site-settings/", {
            "google_login_enabled": "on",
            "google_client_id": "abc.apps.googleusercontent.com",
            "google_client_secret": "shh",
            "code_login_enabled": "on",
            "email_host": "smtp.gmail.com", "email_port": "587", "email_use_tls": "on",
            "email_host_user": "av@example.com", "email_host_password": "apppass",
            "default_from_email": "",
            "backup_enabled": "on", "backup_interval_hours": "12", "backup_keep": "7",
            "ssl_domain": "", "acme_method": "dns01", "cloudflare_api_token": "",
            "acme_staging": "on", "acme_contact_email": "",
        })
        self.assertRedirects(resp, "/accounts/site-settings/")
        cfg = SiteConfig.load()
        self.assertTrue(cfg.google_ready)
        self.assertEqual(cfg.backup_interval_hours, 12)
        self.assertEqual(cfg.from_email, "av@example.com")

    def test_blank_secret_keeps_existing(self):
        cfg = SiteConfig.load()
        cfg.email_host_password = "original"
        cfg.save()
        self.client.login(username="admin", password="pw")
        self.client.post("/accounts/site-settings/", {
            "code_login_enabled": "on",
            "email_host": "smtp.gmail.com", "email_port": "587", "email_use_tls": "on",
            "email_host_user": "av@example.com", "email_host_password": "",
            "google_client_id": "", "google_client_secret": "",
            "default_from_email": "",
            "backup_enabled": "on", "backup_interval_hours": "24", "backup_keep": "14",
            "ssl_domain": "", "acme_method": "dns01", "cloudflare_api_token": "",
            "acme_staging": "on", "acme_contact_email": "",
        })
        cfg.refresh_from_db()
        self.assertEqual(cfg.email_host_password, "original")

    def test_test_email_endpoint(self):
        self.client.login(username="admin", password="pw")
        resp = self.client.post("/accounts/site-settings/test-email")
        self.assertRedirects(resp, "/accounts/site-settings/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("admin@example.com", mail.outbox[0].to)


class AuthToggleTests(TestCase):
    def test_code_login_disabled_blocks_pages(self):
        cfg = SiteConfig.load()
        cfg.code_login_enabled = False
        cfg.save()
        resp = self.client.get("/accounts/login/code/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])

    def test_code_login_enabled_allows_pages(self):
        self.assertEqual(self.client.get("/accounts/login/code/").status_code, 200)

    def test_google_apps_follow_config(self):
        from accounts.adapters import SocialAccountAdapter
        adapter = SocialAccountAdapter()
        self.assertEqual(adapter.list_apps(None, provider="google"), [])

        cfg = SiteConfig.load()
        cfg.google_login_enabled = True
        cfg.google_client_id = "id123"
        cfg.google_client_secret = "sec"
        cfg.save()
        apps = adapter.list_apps(None, provider="google")
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0].client_id, "id123")

    def test_login_page_hides_disabled_methods(self):
        resp = self.client.get("/accounts/login/")
        self.assertNotContains(resp, "Sign in with Google")  # no creds configured
        self.assertContains(resp, "Email me a sign-in code")

        cfg = SiteConfig.load()
        cfg.code_login_enabled = False
        cfg.save()
        resp = self.client.get("/accounts/login/")
        self.assertNotContains(resp, "Email me a sign-in code")