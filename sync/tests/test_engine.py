from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase

from events.models import ChecklistItem, Event, Room, ScheduleItem
from sync.engine import sync_event


def sheet_data(**overrides):
    data = {
        "rooms": [
            {"name": "Mainstage", "room_number": "4AB", "building": "Arch", "floor": "4"},
            {"name": "Prog Panels", "room_number": "303", "building": "Arch", "floor": "3"},
        ],
        "equipment": [
            {"building": "Arch", "room_name": "Mainstage", "room_number": "4AB",
             "vendor": "Shure", "equipment_type": "Audio", "quantity": 2, "item_name": "SM58"},
            {"building": "Arch", "room_name": "Ghost", "room_number": "999",
             "vendor": "", "equipment_type": "Video", "quantity": 1, "item_name": "Orphan Projector"},
        ],
        "schedule": [
            {"title": "Opening", "room_name": "Mainstage", "room_number": "4AB", "building": "Arch",
             "av": "Yes", "description": "", "date": "4/3/2026", "start_time": "10:00 AM", "end_time": "11:00 AM"},
            {"title": "Late Show", "room_name": "Mainstage", "room_number": "4AB", "building": "Arch",
             "av": "Yes", "description": "", "date": "4/3/2026", "start_time": "11:45 PM", "end_time": "12:45 AM"},
            {"title": "In The Hallway", "room_name": "Hallway", "room_number": "", "building": "Arch",
             "av": "No", "description": "", "date": "4/3/2026", "start_time": "1:00 PM", "end_time": "2:00 PM"},
            {"title": "Broken Row", "room_name": "Mainstage", "room_number": "4AB", "building": "Arch",
             "av": "Yes", "description": "", "date": "someday", "start_time": "1:00 PM", "end_time": "2:00 PM"},
        ],
        "staff": [
            {"staff_name": "Kit Zeller", "date": "4/3/2026", "start_time": "9:00 AM",
             "end_time": "2:00 PM", "notes": ""},
        ],
        "checklist": [
            {"building": "Arch", "room_name": "Mainstage", "room_number": "4AB",
             "item": "Mic check", "checked": False, "checked_by": "", "checked_at": ""},
        ],
    }
    data.update(overrides)
    return data


class EngineTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(
            name="Test Con", slug="test-con", spreadsheet_id="fake-id",
        )

    def run_sync(self, data):
        with patch("sync.engine.fetch_event_sheets", return_value=data):
            sync_event(self.event)
        self.event.refresh_from_db()

    def test_basic_sync(self):
        self.run_sync(sheet_data())
        self.assertEqual(self.event.last_sync_status, "success")
        self.assertEqual(self.event.rooms.count(), 2)
        self.assertEqual(self.event.schedule_items.count(), 3)  # broken row skipped
        self.assertEqual(self.event.staff_shifts.count(), 1)

    def test_midnight_crossing_and_av_parse(self):
        self.run_sync(sheet_data())
        late = self.event.schedule_items.get(title="Late Show")
        tz = self.event.tz
        self.assertGreater(late.ends_at.astimezone(tz).date(), late.starts_at.astimezone(tz).date())
        self.assertGreater(late.ends_at, late.starts_at)
        self.assertTrue(late.has_av)

    def test_room_fk_resolution_and_denorm_fallback(self):
        self.run_sync(sheet_data())
        opening = self.event.schedule_items.get(title="Opening")
        self.assertIsNotNone(opening.room)
        hallway = self.event.schedule_items.get(title="In The Hallway")
        self.assertIsNone(hallway.room)
        self.assertEqual(hallway.room_name, "Hallway")  # denorm fallback intact

    def test_warnings_recorded_not_silent(self):
        self.run_sync(sheet_data())
        self.assertIn("Orphan Projector", self.event.last_sync_error)
        self.assertIn("Broken Row", self.event.last_sync_error)

    def test_room_upsert_preserves_image_and_checked_items(self):
        self.run_sync(sheet_data())
        room = self.event.rooms.get(room_number="4AB")
        room.layout_image.save("layout.png", ContentFile(b"fake-png"))
        item = room.checklist_items.get()
        item.checked = True
        item.checked_by = "kit"
        item.save()

        # Re-sync with 4AB removed from the Rooms tab AND checklist tab missing
        data = sheet_data()
        data["rooms"] = [r for r in data["rooms"] if r["room_number"] != "4AB"]
        data["checklist"] = None
        self.run_sync(data)

        room.refresh_from_db()  # still exists: has image + checked item
        self.assertTrue(room.layout_image)
        self.assertTrue(room.checklist_items.filter(checked=True).exists())
        self.assertIn("kept", self.event.last_sync_error)

    def test_room_with_setup_status_survives_removal(self):
        self.run_sync(sheet_data())
        room = self.event.rooms.get(room_number="303")
        room.setup_status = "ready"
        room.save()
        data = sheet_data()
        data["rooms"] = [r for r in data["rooms"] if r["room_number"] != "303"]
        self.run_sync(data)
        self.assertTrue(self.event.rooms.filter(room_number="303").exists())

    def test_cancelled_title_parsed(self):
        data = sheet_data()
        data["schedule"].append({
            "title": "CANCELLED Karaoke Finals", "room_name": "Mainstage", "room_number": "4AB",
            "building": "Arch", "av": "Yes", "description": "",
            "date": "4/3/2026", "start_time": "3:00 PM", "end_time": "4:00 PM",
        })
        self.run_sync(data)
        item = self.event.schedule_items.get(title="Karaoke Finals")
        self.assertTrue(item.is_cancelled)

    def test_removed_plain_room_is_deleted(self):
        self.run_sync(sheet_data())
        data = sheet_data()
        data["rooms"] = [r for r in data["rooms"] if r["room_number"] != "303"]
        self.run_sync(data)
        self.assertFalse(self.event.rooms.filter(room_number="303").exists())

    def test_sheetless_event_skipped(self):
        event = Event.objects.create(name="No Sheet", slug="no-sheet")
        sync_event(event)  # must not raise or touch status
        event.refresh_from_db()
        self.assertEqual(event.last_sync_status, "")
