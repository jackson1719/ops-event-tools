from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from events.models import ChecklistItem, Event, Room


class EscHelperTests(TestCase):
    """The client-side esc() helpers must encode quotes (values land in
    title="..."/value="..." attributes) — regression for the stored-XSS fix."""

    def _assert_attr_safe(self, text):
        self.assertIn("&quot;", text, "esc() must encode double quotes")
        self.assertIn("&#39;", text, "esc() must encode single quotes")
        # The old textContent->innerHTML implementation must be gone
        self.assertNotIn("d.textContent = str;\n    return d.innerHTML", text)

    def test_live_js(self):
        self._assert_attr_safe((settings.BASE_DIR / "static/js/live.js").read_text())

    def test_live_html_and_timeline(self):
        self._assert_attr_safe((settings.BASE_DIR / "templates/live.html").read_text())
        self._assert_attr_safe((settings.BASE_DIR / "templates/partials/staff_timeline.html").read_text())


class ChecklistEmptyReadGuardTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(name="C", slug="c", spreadsheet_id="x")
        self.room = Room.objects.create(event=self.event, building="B", room_number="1")
        ChecklistItem.objects.create(room=self.room, item="Mic check", checked=True)

    def test_empty_checklist_read_preserves_existing(self):
        from sync.engine import sync_event
        from sync.tests.test_engine import sheet_data

        data = sheet_data()
        data["rooms"] = [{"name": "", "room_number": "1", "building": "B", "floor": ""}]
        data["equipment"] = []
        data["schedule"] = []
        data["staff"] = []
        data["checklist"] = []  # transient empty read

        with patch("sync.engine.fetch_event_sheets", return_value=data):
            sync_event(self.event)

        self.assertTrue(ChecklistItem.objects.filter(room__event=self.event).exists())
        self.event.refresh_from_db()
        self.assertIn("keeping existing checklist", self.event.last_sync_error)


class SingleRunnerLockTests(TestCase):
    def test_second_acquire_fails(self):
        from sync.locks import single_runner
        self.assertTrue(single_runner("test-runner-xyz"))
        self.assertFalse(single_runner("test-runner-xyz"))

    def test_exclusive_blocks_reentry(self):
        from sync.locks import Locked, exclusive
        with exclusive("test-excl"):
            with self.assertRaises(Locked):
                with exclusive("test-excl"):
                    pass
