from django.contrib.auth.models import Group
from django.test import TestCase

from accounts.models import User
from events.models import Event


class UserManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = Event.objects.create(name="Test Con", slug="test-con")
        for role in ["Manager", "Admin"]:
            u = User.objects.create_user(role.lower(), password="pw")
            u.groups.add(Group.objects.get(name=role))

    def test_manager_cannot_access_users(self):
        self.client.login(username="manager", password="pw")
        self.assertEqual(self.client.get("/accounts/users/").status_code, 403)

    def test_admin_creates_user_with_role(self):
        self.client.login(username="admin", password="pw")
        resp = self.client.post("/accounts/users/new", {
            "username": "newstaffer",
            "role": "Staff",
            "staff_name": "Kit Zeller",
            "is_active": "on",
            "password": "a-good-password-42",
        })
        self.assertRedirects(resp, "/accounts/users/")
        user = User.objects.get(username="newstaffer")
        self.assertTrue(user.groups.filter(name="Staff").exists())
        self.assertEqual(user.staff_name, "Kit Zeller")
        self.assertFalse(user.is_staff)  # Staff role gets no admin access
        self.assertTrue(self.client_class().login(username="newstaffer", password="a-good-password-42"))

    def test_role_change_updates_groups_and_is_staff(self):
        self.client.login(username="admin", password="pw")
        target = User.objects.create_user("upgrademe", password="pw")
        target.groups.add(Group.objects.get(name="Viewer"))
        resp = self.client.post(f"/accounts/users/{target.pk}/", {
            "username": "upgrademe", "role": "Manager", "staff_name": "",
            "is_active": "on", "password": "",
        })
        self.assertRedirects(resp, "/accounts/users/")
        target.refresh_from_db()
        self.assertTrue(target.groups.filter(name="Manager").exists())
        self.assertFalse(target.groups.filter(name="Viewer").exists())
        self.assertTrue(target.is_staff)

    def test_cannot_deactivate_self(self):
        self.client.login(username="admin", password="pw")
        admin = User.objects.get(username="admin")
        self.client.post(f"/accounts/users/{admin.pk}/", {
            "username": "admin", "role": "Admin", "staff_name": "",
            "password": "",  # is_active omitted = unchecked
        })
        admin.refresh_from_db()
        self.assertTrue(admin.is_active)


class EventSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = Event.objects.create(name="Test Con", slug="test-con")
        for role in ["Staff", "Manager", "Admin"]:
            u = User.objects.create_user(role.lower(), password="pw")
            u.groups.add(Group.objects.get(name=role))

    def test_staff_cannot_edit_settings(self):
        self.client.login(username="staff", password="pw")
        self.assertEqual(self.client.get(f"/e/{self.event.slug}/manage/settings").status_code, 403)

    def test_manager_updates_timezone(self):
        self.client.login(username="manager", password="pw")
        resp = self.client.post(f"/e/{self.event.slug}/manage/settings", {
            "name": "Test Con", "timezone": "America/New_York", "is_active": "on",
            "spreadsheet_id": "", "rooms_tab": "Rooms", "equipment_tab": "Equipment",
            "schedule_tab": "Events", "staff_tab": "Staff Shifts", "checklist_tab": "",
        })
        self.assertEqual(resp.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.timezone, "America/New_York")

    def test_invalid_timezone_rejected(self):
        self.client.login(username="manager", password="pw")
        resp = self.client.post(f"/e/{self.event.slug}/manage/settings", {
            "name": "Test Con", "timezone": "Pacific/Narnia", "is_active": "on",
            "spreadsheet_id": "", "rooms_tab": "Rooms", "equipment_tab": "Equipment",
            "schedule_tab": "Events", "staff_tab": "Staff Shifts", "checklist_tab": "",
        })
        self.assertContains(resp, "Unknown timezone")

    def test_event_create_admin_only(self):
        self.client.login(username="manager", password="pw")
        self.assertEqual(self.client.get("/events/new").status_code, 403)
        self.client.login(username="admin", password="pw")
        resp = self.client.post("/events/new", {
            "name": "New Con", "slug": "new-con",
            "timezone": "America/Los_Angeles", "spreadsheet_id": "",
        })
        self.assertRedirects(resp, "/e/new-con/manage/settings")
        self.assertTrue(Event.objects.filter(slug="new-con").exists())

    def test_audit_page_renders(self):
        self.client.login(username="manager", password="pw")
        self.assertEqual(self.client.get(f"/e/{self.event.slug}/manage/audit").status_code, 200)
