from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group
from django.test import TestCase

from accounts.models import AcmeChallenge, SiteConfig, User
from sync import acme_client
from sync.cloudflare_dns import CloudflareError, create_txt_record, find_zone_id


def make_self_signed(domain="test.example.com", days=90) -> str:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)])
    now = datetime.now(dt_timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=days))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


class ChallengeRouteTests(TestCase):
    def test_serves_key_authorization_anonymously(self):
        AcmeChallenge.objects.create(token="tok123", key_authorization="tok123.thumb")
        resp = self.client.get("/.well-known/acme-challenge/tok123")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"tok123.thumb")
        self.assertEqual(resp["Content-Type"], "text/plain")

    def test_unknown_token_404(self):
        resp = self.client.get("/.well-known/acme-challenge/nope")
        self.assertEqual(resp.status_code, 404)


class CloudflareDnsTests(TestCase):
    def _resp(self, payload):
        mock = MagicMock()
        mock.json.return_value = payload
        return mock

    def test_find_zone_walks_up(self):
        with patch("sync.cloudflare_dns.requests.get") as get:
            get.side_effect = [
                self._resp({"success": True, "result": []}),                       # sc-lan.edolas.org
                self._resp({"success": True, "result": [{"id": "zone42"}]}),       # edolas.org
            ]
            zone = find_zone_id("tok", "sc-lan.edolas.org")
        self.assertEqual(zone, "zone42")
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer tok")

    def test_find_zone_not_found_raises(self):
        with patch("sync.cloudflare_dns.requests.get") as get:
            get.return_value = self._resp({"success": True, "result": []})
            with self.assertRaises(CloudflareError):
                find_zone_id("tok", "nope.example.com")

    def test_create_txt_record(self):
        with patch("sync.cloudflare_dns.requests.post") as post:
            post.return_value = self._resp({"success": True, "result": {"id": "rec1"}})
            record_id = create_txt_record("tok", "zone42", "_acme-challenge.x", "val")
        self.assertEqual(record_id, "rec1")
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["type"], "TXT")
        self.assertEqual(body["content"], "val")


class RenewalDueTests(TestCase):
    def test_no_cert_is_due(self):
        self.assertTrue(acme_client.renewal_due())

    def test_fresh_cert_not_due_expiring_cert_due(self):
        acme_client.fullchain_path().write_text(make_self_signed(days=90))
        self.assertFalse(acme_client.renewal_due())
        acme_client.fullchain_path().write_text(make_self_signed(days=20))
        self.assertTrue(acme_client.renewal_due())

    def test_renew_if_needed_skips_when_not_ready(self):
        # ssl not enabled -> no issuance attempted even with no cert
        with patch.object(acme_client, "issue_certificate") as issue:
            self.assertFalse(acme_client.renew_if_needed())
            issue.assert_not_called()


class IssueFlowTests(TestCase):
    def setUp(self):
        cfg = SiteConfig.load()
        cfg.ssl_enabled = True
        cfg.ssl_domain = "test.example.com"
        cfg.acme_method = "http01"
        cfg.save()

    def test_http01_flow_writes_and_cleans_challenge(self):
        from django.test import override_settings
        self.enterContext(override_settings(ALLOWED_HOSTS=["test.example.com", "testserver"]))

        chall = MagicMock()
        chall.chall.encode.return_value = "tokenA"
        chall.chall.key_authorization.return_value = "tokenA.kthumb"
        authorization = MagicMock()
        authorization.body.challenges = [MagicMock(typ="dns-01"), chall]
        chall.typ = "http-01"

        order = MagicMock(authorizations=[authorization])
        finalized = MagicMock(fullchain_pem=make_self_signed())

        fake_client = MagicMock()
        fake_client.new_order.return_value = order
        fake_client.poll_and_finalize.return_value = finalized

        seen_during_answer = {}

        def answer(challenge_body, response):
            seen_during_answer["row"] = AcmeChallenge.objects.filter(token="tokenA").exists()

        fake_client.answer_challenge.side_effect = answer

        with patch.object(acme_client, "_make_client", return_value=fake_client), \
             patch.object(acme_client, "_make_csr", side_effect=lambda d: (
                 acme_client.privkey_path().with_suffix(".pem.new").write_bytes(b"key") or b"csr")), \
             patch.object(acme_client, "reload_ssl_server"):
            acme_client.issue_certificate()

        # Challenge existed while answering, cleaned after
        self.assertTrue(seen_during_answer["row"])
        self.assertFalse(AcmeChallenge.objects.exists())
        # Cert written, status recorded
        self.assertTrue(acme_client.fullchain_path().exists())
        cfg = SiteConfig.load()
        self.assertEqual(cfg.acme_last_status, "success")
        self.assertIsNotNone(cfg.cert_expires_at)

    def test_error_recorded_on_failure(self):
        cfg = SiteConfig.load()
        cfg.ssl_domain = ""
        cfg.save()
        with self.assertRaises(RuntimeError):
            acme_client.issue_certificate()
        cfg.refresh_from_db()
        self.assertEqual(cfg.acme_last_status, "error")
        self.assertIn("No domain", cfg.acme_last_error)


class SslSiteSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        admin = User.objects.create_user("admin", password="pw")
        admin.groups.add(Group.objects.get(name="Admin"))

    def test_issue_endpoint_requires_config(self):
        self.client.login(username="admin", password="pw")
        resp = self.client.post("/accounts/site-settings/issue-cert", follow=True)
        self.assertContains(resp, "Complete the HTTPS configuration")

    def test_issue_endpoint_admin_only(self):
        resp = self.client.post("/accounts/site-settings/issue-cert")
        self.assertEqual(resp.status_code, 302)  # anonymous -> login

    def test_ssl_fields_save_and_token_kept_when_blank(self):
        cfg = SiteConfig.load()
        cfg.cloudflare_api_token = "cf-secret"
        cfg.save()
        self.client.login(username="admin", password="pw")
        self.client.post("/accounts/site-settings/", {
            "code_login_enabled": "on",
            "email_host": "smtp.gmail.com", "email_port": "587", "email_use_tls": "on",
            "email_host_user": "", "email_host_password": "",
            "google_client_id": "", "google_client_secret": "",
            "default_from_email": "",
            "backup_enabled": "on", "backup_interval_hours": "24", "backup_keep": "14",
            "ssl_enabled": "on", "ssl_domain": "SC-LAN.Edolas.Org.",
            "acme_method": "dns01", "cloudflare_api_token": "",
            "acme_staging": "on", "acme_contact_email": "",
        })
        cfg.refresh_from_db()
        self.assertTrue(cfg.ssl_enabled)
        self.assertEqual(cfg.ssl_domain, "sc-lan.edolas.org")  # normalized
        self.assertEqual(cfg.cloudflare_api_token, "cf-secret")  # kept
        self.assertTrue(cfg.ssl_ready)
