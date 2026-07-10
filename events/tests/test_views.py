import zoneinfo
from datetime import datetime

from django.contrib.auth.models import Group
from django.test import TestCase

from accounts.models import User
from events.models import Event, Room, ScheduleItem

TZ = zoneinfo.ZoneInfo("America/Los_Angeles")


class ViewSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = Event.objects.create(name="Test Con", slug="test-con")
        cls.room = Room.objects.create(
            event=cls.event, building="Summit", room_number="340-342", name="Prog Panels",
        )
        ScheduleItem.objects.create(
            event=cls.event, room=cls.room,
            building="Summit", room_name="Prog Panels", room_number="340-342",
            title="Test Panel", has_av=True,
            starts_at=datetime(2026, 4, 3, 10, 0, tzinfo=TZ),
            ends_at=datetime(2026, 4, 3, 11, 0, tzinfo=TZ),
        )
        cls.viewer = User.objects.create_user("v", password="pw")
        cls.viewer.groups.add(Group.objects.get(name="Viewer"))

    def setUp(self):
        self.client.login(username="v", password="pw")

    def test_live_renders_with_payload(self):
        resp = self.client.get(f"/e/{self.event.slug}/live?date=2026-04-03&av=")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Test Panel")
        self.assertContains(resp, 'id="events-data"')

    def test_schedule_defaults_today_when_no_filters(self):
        resp = self.client.get(f"/e/{self.event.slug}/schedule")
        self.assertEqual(resp.status_code, 200)

    def test_schedule_table_filters(self):
        resp = self.client.get(
            f"/e/{self.event.slug}/schedule/table",
            {"building": "Summit", "room_number": "340-342", "av": "yes"},
        )
        self.assertContains(resp, "Test Panel")
        resp = self.client.get(f"/e/{self.event.slug}/schedule/table", {"av": "no"})
        self.assertNotContains(resp, "Test Panel")

    def test_room_detail_shows_schedule(self):
        resp = self.client.get(f"/e/{self.event.slug}/rooms/{self.room.pk}")
        self.assertContains(resp, "Test Panel")

    def test_unknown_event_404(self):
        resp = self.client.get("/e/not-a-con/live")
        self.assertEqual(resp.status_code, 404)

    def test_picker_redirects_single_event(self):
        resp = self.client.get("/")
        self.assertRedirects(resp, f"/e/{self.event.slug}/live")
