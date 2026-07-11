from unittest.mock import patch

from django.test import TestCase

from events.models import Event, ScheduleChange
from sync.engine import sync_event
from sync.tests.test_engine import sheet_data


class ScheduleChangeTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(name="Test Con", slug="test-con", spreadsheet_id="fake")

    def run_sync(self, data):
        with patch("sync.engine.fetch_event_sheets", return_value=data):
            sync_event(self.event)

    def changes(self):
        return ScheduleChange.objects.filter(event=self.event)

    def test_first_sync_records_no_changes(self):
        self.run_sync(sheet_data())
        self.assertEqual(self.changes().count(), 0)

    def test_no_changes_when_identical(self):
        self.run_sync(sheet_data())
        self.run_sync(sheet_data())
        self.assertEqual(self.changes().count(), 0)

    def test_time_change_detected(self):
        self.run_sync(sheet_data())
        data = sheet_data()
        data["schedule"][0]["start_time"] = "11:00 AM"
        data["schedule"][0]["end_time"] = "12:00 PM"
        self.run_sync(data)
        change = self.changes().get()
        self.assertEqual(change.change_type, "time_changed")
        self.assertEqual(change.title, "Opening")
        self.assertIn("→", change.detail)

    def test_room_change_detected(self):
        self.run_sync(sheet_data())
        data = sheet_data()
        data["schedule"][0]["room_number"] = "303"
        data["schedule"][0]["room_name"] = "Prog Panels"
        self.run_sync(data)
        change = self.changes().get()
        self.assertEqual(change.change_type, "room_changed")
        self.assertIn("Mainstage (4AB)", change.detail)

    def test_add_and_remove_detected(self):
        self.run_sync(sheet_data())
        data = sheet_data()
        removed = data["schedule"].pop(0)  # remove "Opening"
        data["schedule"].append({
            "title": "Brand New Panel", "room_name": "Mainstage", "room_number": "4AB",
            "building": "Arch", "av": "Yes", "description": "",
            "date": "4/3/2026", "start_time": "5:00 PM", "end_time": "6:00 PM",
        })
        self.run_sync(data)
        types = {c.change_type: c for c in self.changes()}
        self.assertEqual(set(types), {"added", "removed"})
        self.assertEqual(types["removed"].title, removed["title"])
        self.assertEqual(types["added"].title, "Brand New Panel")

    def test_cancellation_detected(self):
        self.run_sync(sheet_data())
        data = sheet_data()
        data["schedule"][0]["title"] = "CANCELLED " + data["schedule"][0]["title"]
        self.run_sync(data)
        change = self.changes().get()
        self.assertEqual(change.change_type, "cancelled")
        self.assertEqual(change.title, "Opening")

    def test_duplicate_titles_matched_by_room(self):
        # Two STRIKE rows in different rooms; only one moves in time
        data = sheet_data()
        for room_number in ("4AB", "303"):
            data["schedule"].append({
                "title": "STRIKE", "room_name": "X", "room_number": room_number,
                "building": "Arch", "av": "Yes", "description": "",
                "date": "4/5/2026", "start_time": "4:00 PM", "end_time": "7:00 PM",
            })
        self.run_sync(data)
        data2 = sheet_data()
        for room_number, start in (("4AB", "4:00 PM"), ("303", "5:00 PM")):
            data2["schedule"].append({
                "title": "STRIKE", "room_name": "X", "room_number": room_number,
                "building": "Arch", "av": "Yes", "description": "",
                "date": "4/5/2026", "start_time": start, "end_time": "7:00 PM",
            })
        self.run_sync(data2)
        change = self.changes().get()
        self.assertEqual(change.change_type, "time_changed")
        self.assertEqual(change.room_label, "X (303)")
