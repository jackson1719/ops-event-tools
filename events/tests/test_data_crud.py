import zoneinfo
from datetime import datetime

from django.contrib.auth.models import Group
from django.test import TestCase

from accounts.models import User
from events.models import Event, Room, ScheduleItem, StaffShift

TZ = zoneinfo.ZoneInfo("America/Los_Angeles")


class DataCrudTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = Event.objects.create(name="Test Con", slug="test-con")
        cls.room = Room.objects.create(event=cls.event, building="Summit", room_number="330", name="Workshop")
        for role in ["Staff", "Manager"]:
            u = User.objects.create_user(role.lower(), password="pw")
            u.groups.add(Group.objects.get(name=role))

    def setUp(self):
        self.client.login(username="manager", password="pw")

    def url(self, path):
        return f"/e/{self.event.slug}/manage/data{path}"

    def test_staff_gets_403(self):
        self.client.login(username="staff", password="pw")
        for path in ["/rooms", "/schedule", "/shifts"]:
            self.assertEqual(self.client.get(self.url(path)).status_code, 403)

    def test_room_create_and_equipment_edit(self):
        resp = self.client.post(self.url("/rooms/new"), {
            "building": "Arch", "room_number": "6C", "name": "AMV Theater", "floor": "6",
        })
        room = Room.objects.get(room_number="6C")
        self.assertRedirects(resp, self.url(f"/rooms/{room.pk}"))

        # Add equipment via the inline formset
        resp = self.client.post(self.url(f"/rooms/{room.pk}"), {
            "building": "Arch", "room_number": "6C", "name": "AMV Theater", "floor": "6",
            "eq-TOTAL_FORMS": "1", "eq-INITIAL_FORMS": "0", "eq-MIN_NUM_FORMS": "0", "eq-MAX_NUM_FORMS": "1000",
            "eq-0-equipment_type": "Audio", "eq-0-quantity": "2", "eq-0-item_name": "SM58", "eq-0-vendor": "Shure",
            "cl-TOTAL_FORMS": "1", "cl-INITIAL_FORMS": "0", "cl-MIN_NUM_FORMS": "0", "cl-MAX_NUM_FORMS": "1000",
            "cl-0-position": "0", "cl-0-item": "Mic check",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(room.equipment.count(), 1)
        self.assertEqual(room.checklist_items.count(), 1)

    def test_schedule_item_create_resolves_room_fk(self):
        resp = self.client.post(self.url("/schedule/new"), {
            "title": "Manual Panel", "building": "Summit", "room_name": "Workshop", "room_number": "330",
            "starts_at": "2026-04-03T10:00", "ends_at": "2026-04-03T11:00",
            "has_av": "on", "description": "",
        })
        self.assertRedirects(resp, self.url("/schedule"))
        item = ScheduleItem.objects.get(title="Manual Panel")
        self.assertEqual(item.room, self.room)
        # datetime-local input interpreted in event tz (PDT)
        self.assertEqual(item.starts_at.astimezone(TZ).hour, 10)

    def test_schedule_end_before_start_rejected(self):
        resp = self.client.post(self.url("/schedule/new"), {
            "title": "Bad Panel", "building": "", "room_name": "", "room_number": "",
            "starts_at": "2026-04-03T11:00", "ends_at": "2026-04-03T10:00", "description": "",
        })
        self.assertContains(resp, "End must be after start")

    def test_shift_crud(self):
        resp = self.client.post(self.url("/shifts/new"), {
            "staff_name": "Kit Zeller",
            "starts_at": "2026-04-03T09:00", "ends_at": "2026-04-03T14:00", "notes": "",
        })
        self.assertRedirects(resp, self.url("/shifts"))
        shift = StaffShift.objects.get(staff_name="Kit Zeller")
        resp = self.client.post(self.url(f"/shifts/{shift.pk}/delete"))
        self.assertEqual(StaffShift.objects.count(), 0)

    def test_room_delete(self):
        doomed = Room.objects.create(event=self.event, building="X", room_number="1")
        self.client.post(self.url(f"/rooms/{doomed.pk}/delete"))
        self.assertFalse(Room.objects.filter(pk=doomed.pk).exists())
