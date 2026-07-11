import zoneinfo
from datetime import datetime

from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.test import TestCase

from accounts.models import User
from events.models import AuditLog, ChecklistItem, Equipment, Event, Link, Room, StaffShift
from events.services import clone_event
from sync.engine import split_cancelled

TZ = zoneinfo.ZoneInfo("America/Los_Angeles")


class CancelledParseTests(TestCase):
    def test_split_cancelled(self):
        self.assertEqual(split_cancelled("CANCELLED Just Dance!"), ("Just Dance!", True))
        self.assertEqual(split_cancelled("cancelled: Panel X"), ("Panel X", True))
        self.assertEqual(split_cancelled("CANCELLED - Panel Y"), ("Panel Y", True))
        self.assertEqual(split_cancelled("Normal Panel"), ("Normal Panel", False))
        # A title that mentions cancellation mid-string is not cancelled
        self.assertEqual(split_cancelled("How Panels Get Cancelled"), ("How Panels Get Cancelled", False))


class CloneEventTests(TestCase):
    def setUp(self):
        self.source = Event.objects.create(name="Con 2026", slug="con-2026", spreadsheet_id="abc")
        room = Room.objects.create(event=self.source, building="Summit", room_number="330", name="Workshop")
        room.layout_image.save("layout.png", ContentFile(b"png-bytes"))
        Equipment.objects.create(room=room, item_name="SM58", equipment_type="Audio", quantity=2)
        ChecklistItem.objects.create(room=room, item="Mic check", checked=True, checked_by="kit")
        Link.objects.create(event=self.source, title="Radio channels", url="https://example.com")
        StaffShift.objects.create(
            event=self.source, staff_name="Kit",
            starts_at=datetime(2026, 4, 3, 9, 0, tzinfo=TZ),
            ends_at=datetime(2026, 4, 3, 14, 0, tzinfo=TZ),
        )

    def test_clone_copies_setup_not_program(self):
        new = clone_event(self.source, "con-2027", "Con 2027")
        self.assertEqual(new.rooms.count(), 1)
        new_room = new.rooms.get()
        self.assertTrue(new_room.layout_image)
        self.assertNotEqual(new_room.layout_image.name, self.source.rooms.get().layout_image.name)
        self.assertEqual(new_room.equipment.count(), 1)
        # Checklist copied but reset
        item = new_room.checklist_items.get()
        self.assertFalse(item.checked)
        self.assertEqual(item.checked_by, "")
        self.assertEqual(new.links.count(), 1)
        # Program data NOT copied; sheet connection left blank
        self.assertEqual(new.schedule_items.count(), 0)
        self.assertEqual(new.staff_shifts.count(), 0)
        self.assertEqual(new.spreadsheet_id, "")


class RoomStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = Event.objects.create(name="Test Con", slug="test-con")
        cls.room = Room.objects.create(event=cls.event, building="Summit", room_number="330")
        for role in ["Viewer", "Staff"]:
            u = User.objects.create_user(role.lower(), password="pw")
            u.groups.add(Group.objects.get(name=role))

    def test_staff_can_set_status_and_audit_recorded(self):
        self.client.login(username="staff", password="pw")
        resp = self.client.post(
            f"/e/{self.event.slug}/rooms/{self.room.pk}/status",
            {"status": "ready", "note": "all good"},
        )
        self.assertEqual(resp.status_code, 204)
        self.room.refresh_from_db()
        self.assertEqual(self.room.setup_status, "ready")
        self.assertEqual(self.room.status_updated_by, "staff")
        log = AuditLog.objects.get(action="room_status")
        self.assertIn("Ready", log.detail)

    def test_viewer_cannot_set_status(self):
        self.client.login(username="viewer", password="pw")
        resp = self.client.post(
            f"/e/{self.event.slug}/rooms/{self.room.pk}/status", {"status": "ready"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_invalid_status_rejected(self):
        self.client.login(username="staff", password="pw")
        resp = self.client.post(
            f"/e/{self.event.slug}/rooms/{self.room.pk}/status", {"status": "bogus"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_status_board_renders_for_staff(self):
        self.client.login(username="staff", password="pw")
        resp = self.client.get(f"/e/{self.event.slug}/status")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "330")

    def test_checklist_toggle_writes_audit(self):
        item = ChecklistItem.objects.create(room=self.room, item="Mic check")
        self.client.login(username="staff", password="pw")
        resp = self.client.post(
            f"/e/{self.event.slug}/checklist/{item.pk}/toggle", {"checked": "1"},
        )
        self.assertEqual(resp.status_code, 204)
        self.assertTrue(AuditLog.objects.filter(action="checklist").exists())


class MyShiftsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = Event.objects.create(name="Test Con", slug="test-con")
        cls.shift = StaffShift.objects.create(
            event=cls.event, staff_name="Kit Zeller",
            starts_at=datetime(2026, 4, 3, 9, 0, tzinfo=TZ),
            ends_at=datetime(2026, 4, 3, 14, 0, tzinfo=TZ),
            notes="Coordinator",
        )
        cls.user = User.objects.create_user("kit", password="pw", staff_name="Kit Zeller")
        cls.user.groups.add(Group.objects.get(name="Staff"))

    def test_my_shifts_shows_linked_shifts(self):
        self.client.login(username="kit", password="pw")
        resp = self.client.get(f"/e/{self.event.slug}/staff/mine")
        self.assertContains(resp, "Coordinator")
        self.assertContains(resp, "my.ics")

    def test_ics_with_token_no_login(self):
        token = self.user.get_or_create_ical_token()
        resp = self.client.get(f"/e/{self.event.slug}/staff/my.ics?token={token}")
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("BEGIN:VCALENDAR", body)
        self.assertIn(f"UID:shift-{self.shift.pk}@ops-event-tools", body)
        # 9 AM PDT == 16:00 UTC
        self.assertIn("DTSTART:20260403T160000Z", body)

    def test_ics_bad_token_404(self):
        resp = self.client.get(f"/e/{self.event.slug}/staff/my.ics?token=wrong")
        self.assertEqual(resp.status_code, 404)
