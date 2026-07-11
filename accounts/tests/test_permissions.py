from django.contrib.auth.models import Group
from django.test import TestCase

from accounts.models import User
from events.models import Event

VIEWER_PAGES = ["/live", "/schedule", "/rooms", "/links"]
STAFF_PAGES = ["/staff", "/staff/on-shift"]
MANAGER_PAGES = ["/manage/", "/manage/links", "/manage/room-images", "/analytics"]


class PermissionMatrixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = Event.objects.create(name="Test Con", slug="test-con")
        for role in ["Viewer", "Staff", "Manager", "Admin"]:
            user = User.objects.create_user(role.lower(), password="pw")
            user.groups.add(Group.objects.get(name=role))

    def url(self, path):
        return f"/e/{self.event.slug}{path}"

    def assert_access(self, username, page, expected):
        client = self.client_class()
        if username:
            client.login(username=username, password="pw")
        resp = client.get(self.url(page))
        self.assertEqual(
            resp.status_code, expected,
            f"{username or 'anonymous'} on {page}: expected {expected}, got {resp.status_code}",
        )

    def test_anonymous_redirected_everywhere(self):
        for page in VIEWER_PAGES + STAFF_PAGES + MANAGER_PAGES:
            self.assert_access(None, page, 302)

    def test_viewer_matrix(self):
        for page in VIEWER_PAGES:
            self.assert_access("viewer", page, 200)
        for page in STAFF_PAGES + MANAGER_PAGES:
            self.assert_access("viewer", page, 403)

    def test_staff_matrix(self):
        for page in VIEWER_PAGES + STAFF_PAGES:
            self.assert_access("staff", page, 200)
        for page in MANAGER_PAGES:
            self.assert_access("staff", page, 403)

    def test_manager_matrix(self):
        for page in VIEWER_PAGES + STAFF_PAGES + MANAGER_PAGES:
            self.assert_access("manager", page, 200)

    def test_admin_matrix(self):
        for page in VIEWER_PAGES + STAFF_PAGES + MANAGER_PAGES:
            self.assert_access("admin", page, 200)

    def test_role_hierarchy_helper(self):
        from accounts.roles import has_role
        manager = User.objects.get(username="manager")
        self.assertTrue(has_role(manager, "Viewer"))
        self.assertTrue(has_role(manager, "Manager"))
        self.assertFalse(has_role(manager, "Admin"))

    def test_theme_selection_persists(self):
        self.client.login(username="viewer", password="pw")
        resp = self.client.post("/accounts/theme/", {"theme": "sakura", "next": self.url("/links")})
        self.assertEqual(resp.status_code, 302)
        user = User.objects.get(username="viewer")
        self.assertEqual(user.theme, "sakura")
        resp = self.client.get(self.url("/links"))
        self.assertContains(resp, 'class="theme-sakura"')
        # Invalid theme ignored
        self.client.post("/accounts/theme/", {"theme": "neon-zebra"})
        user.refresh_from_db()
        self.assertEqual(user.theme, "sakura")

    def test_htmx_partial_gets_hx_redirect_when_logged_out(self):
        resp = self.client.get(self.url("/schedule/table"), HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("/accounts/login/", resp.headers["HX-Redirect"])
