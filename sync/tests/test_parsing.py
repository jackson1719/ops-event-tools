import zoneinfo
from datetime import date, timedelta

from django.test import SimpleTestCase

from events.timeutil import parse_sheet_date, parse_sheet_time, parse_time_range

TZ = zoneinfo.ZoneInfo("America/Los_Angeles")


class ParsingTests(SimpleTestCase):
    def test_date_formats(self):
        self.assertEqual(parse_sheet_date("4/3/2026"), date(2026, 4, 3))
        self.assertEqual(parse_sheet_date("04/03/2026"), date(2026, 4, 3))
        self.assertEqual(parse_sheet_date("2026-04-03"), date(2026, 4, 3))
        self.assertIsNone(parse_sheet_date("April 3rd"))
        self.assertIsNone(parse_sheet_date(""))

    def test_time_formats(self):
        self.assertEqual(parse_sheet_time("9:00 AM").hour, 9)
        self.assertEqual(parse_sheet_time("12:00 AM").hour, 0)
        self.assertEqual(parse_sheet_time("12:00 PM").hour, 12)
        self.assertEqual(parse_sheet_time("14:30").hour, 14)
        self.assertIsNone(parse_sheet_time("noon"))

    def test_normal_range(self):
        starts, ends = parse_time_range(date(2026, 4, 3), "9:00 AM", "4:00 PM", TZ)
        self.assertEqual(starts.hour, 9)
        self.assertEqual(ends.hour, 16)
        self.assertEqual(starts.date(), ends.date())

    def test_midnight_crossing_adds_a_day(self):
        starts, ends = parse_time_range(date(2026, 4, 3), "11:45 PM", "12:45 AM", TZ)
        self.assertEqual(ends - starts, timedelta(hours=1))
        self.assertEqual(ends.date(), date(2026, 4, 4))

    def test_unparseable_returns_none(self):
        self.assertIsNone(parse_time_range(date(2026, 4, 3), "sometime", "later", TZ))
        self.assertIsNone(parse_time_range(None, "9:00 AM", "10:00 AM", TZ))
