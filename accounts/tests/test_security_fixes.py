from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase

from accounts.models import User
from accounts.views import LOGIN_MAX_ATTEMPTS


class LoginThrottleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        u = User.objects.create_user("kit", password="rightpassword-123")
        u.groups.add(Group.objects.get(name="Viewer"))

    def setUp(self):
        cache.clear()

    def test_lockout_after_max_attempts(self):
        for _ in range(LOGIN_MAX_ATTEMPTS):
            resp = self.client.post("/accounts/login/", {"username": "kit", "password": "wrong"})
            self.assertContains(resp, "Invalid username or password")
        # Next attempt is throttled even with the CORRECT password
        resp = self.client.post("/accounts/login/", {"username": "kit", "password": "rightpassword-123"})
        self.assertContains(resp, "Too many failed attempts")
        self.assertFalse(resp.wsgi_request.user.is_authenticated)

    def test_success_clears_counter(self):
        for _ in range(3):
            self.client.post("/accounts/login/", {"username": "kit", "password": "wrong"})
        resp = self.client.post("/accounts/login/", {"username": "kit", "password": "rightpassword-123"})
        self.assertEqual(resp.status_code, 302)  # logged in

    def test_throttle_keyed_on_cf_connecting_ip(self):
        for _ in range(LOGIN_MAX_ATTEMPTS):
            self.client.post("/accounts/login/", {"username": "kit", "password": "wrong"},
                             HTTP_CF_CONNECTING_IP="1.2.3.4")
        # Different client IP is unaffected
        resp = self.client.post("/accounts/login/", {"username": "kit", "password": "rightpassword-123"},
                                HTTP_CF_CONNECTING_IP="5.6.7.8")
        self.assertEqual(resp.status_code, 302)


class LogoutMethodTests(TestCase):
    def test_logout_requires_post(self):
        User.objects.create_user("kit", password="pw").groups.add(Group.objects.get(name="Viewer"))
        self.client.login(username="kit", password="pw")
        self.assertEqual(self.client.get("/accounts/logout/").status_code, 405)
        self.assertEqual(self.client.post("/accounts/logout/").status_code, 302)


class GroupPermissionTests(TestCase):
    def test_role_groups_have_admin_permissions(self):
        # 0007 migration must have assigned model perms (fresh-DB regression)
        self.assertGreater(Group.objects.get(name="Manager").permissions.count(), 0)
        self.assertGreater(Group.objects.get(name="Admin").permissions.count(), 0)


class IcsEscapeTests(TestCase):
    def test_carriage_return_neutralized(self):
        from events.views.staff import _ics_escape
        out = _ics_escape("Fake\r\nBEGIN:VEVENT")
        self.assertNotIn("\r", out)
        self.assertNotIn("\n", out)  # real newlines escaped to literal \n
        self.assertIn("\\n", out)


class MediaPathSlugTests(TestCase):
    def test_room_image_path_strips_separators(self):
        from types import SimpleNamespace
        from events.models import room_image_path
        inst = SimpleNamespace(
            pk=5, building="Summit/../etc", room_number="4 A/B",
            event=SimpleNamespace(slug="con"),
        )
        path = room_image_path(inst, "evil/../x.PNG")
        self.assertNotIn("..", path)
        self.assertNotIn(" ", path)
        self.assertTrue(path.startswith("room_images/con/"))
        self.assertTrue(path.endswith(".png"))
