"""Event-timezone helpers and sheet string parsing.

ALL "now"/"today" logic for event-facing pages must go through event_now /
event_today — never server-local time. Sheet string parsing (multi-format,
ported from the old app's database.py) lives here and is used ONLY by the
sync/import layer; views never parse date/time strings.
"""
from datetime import date, datetime, time, timedelta

DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d")
TIME_FORMATS = ("%I:%M %p", "%H:%M")


def event_now(event) -> datetime:
    """Aware 'now' in the event's timezone."""
    from django.utils import timezone
    return timezone.now().astimezone(event.tz)


def event_today(event) -> date:
    return event_now(event).date()


def parse_sheet_date(value: str) -> date | None:
    value = (value or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_sheet_time(value: str) -> time | None:
    value = (value or "").strip()
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    return None


def combine_aware(d: date, t: time, tz) -> datetime:
    return datetime.combine(d, t).replace(tzinfo=tz)


def parse_time_range(d: date, start_str: str, end_str: str, tz) -> tuple[datetime, datetime] | None:
    """Parse a (date, start, end) sheet triple into aware datetimes.

    Handles midnight crossing: an end time at or before the start time means
    the item runs into the next day (e.g. 11:45 PM - 12:45 AM).
    """
    start_t = parse_sheet_time(start_str)
    end_t = parse_sheet_time(end_str)
    if d is None or start_t is None or end_t is None:
        return None
    starts_at = combine_aware(d, start_t, tz)
    ends_at = combine_aware(d, end_t, tz)
    if ends_at <= starts_at:
        ends_at += timedelta(days=1)
    return starts_at, ends_at


def minutes_since_midnight(dt: datetime, day: date, tz) -> int:
    """Minutes from `day` 00:00 (event tz) to dt — >1440 for cross-midnight ends.

    This preserves the minutes contract that live.js expects.
    """
    midnight = combine_aware(day, time(0, 0), tz)
    return int((dt.astimezone(tz) - midnight).total_seconds() // 60)
