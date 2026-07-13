from django.contrib.auth.models import Group
from django.test import TestCase

from accounts.models import User


class CspHeaderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        u = User.objects.create_user("v", password="pw")
        u.groups.add(Group.objects.get(name="Viewer"))

    def test_login_page_has_nonce_csp(self):
        resp = self.client.get("/accounts/login/")
        csp = resp.headers.get("Content-Security-Policy", "")
        self.assertIn("script-src", csp)
        self.assertIn("'strict-dynamic'", csp)
        self.assertIn("'nonce-", csp)
        self.assertNotIn("'unsafe-inline'", csp.split("style-src")[0])  # not in script-src
        # The nonce in the header matches the one stamped on the page's scripts
        nonce = csp.split("'nonce-")[1].split("'")[0]
        self.assertContains(resp, f'nonce="{nonce}"')

    def test_nonce_is_per_request(self):
        a = self.client.get("/accounts/login/")["Content-Security-Policy"]
        b = self.client.get("/accounts/login/")["Content-Security-Policy"]
        self.assertNotEqual(a, b)

    def test_admin_exempted(self):
        self.client.force_login(User.objects.create_superuser("root", password="pw"))
        resp = self.client.get("/admin/")
        self.assertNotIn("Content-Security-Policy", resp.headers)

    def test_authenticated_page_has_csp(self):
        self.client.login(username="v", password="pw")
        from events.models import Event
        Event.objects.create(name="C", slug="c")
        resp = self.client.get("/e/c/live")
        self.assertIn("Content-Security-Policy", resp.headers)
        self.assertIn("frame-ancestors 'none'", resp.headers["Content-Security-Policy"])
