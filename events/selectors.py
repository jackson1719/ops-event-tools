"""Shared query helpers for event-scoped pages."""
from datetime import date, datetime, time, timedelta

from .models import Event, ScheduleItem, StaffShift
from .timeutil import combine_aware


def format_day(d: date) -> str:
    return d.strftime("%A (%-m/%-d)")


def fmt_time(dt: datetime, tz) -> str:
    return dt.astimezone(tz).strftime("%-I:%M %p")


def day_bounds(event: Event, d: date) -> tuple[datetime, datetime]:
    # Next calendar midnight, not start+24h — correct across DST transitions
    # (a spring-forward day is 23h, fall-back 25h).
    start = combine_aware(d, time(0, 0), event.tz)
    end = combine_aware(d + timedelta(days=1), time(0, 0), event.tz)
    return start, end


def schedule_days(event: Event) -> list[dict]:
    """Distinct days (event tz) that have schedule items, as ISO-value/label dicts."""
    days = []
    seen = set()
    for starts_at in event.schedule_items.values_list("starts_at", flat=True).order_by("starts_at"):
        d = starts_at.astimezone(event.tz).date()
        if d not in seen:
            seen.add(d)
            days.append({"value": d.isoformat(), "label": format_day(d), "date": d})
    return days


def staff_days(event: Event) -> list[dict]:
    days = []
    seen = set()
    for starts_at in event.staff_shifts.values_list("starts_at", flat=True).order_by("starts_at"):
        d = starts_at.astimezone(event.tz).date()
        if d not in seen:
            seen.add(d)
            days.append({"value": d.isoformat(), "label": format_day(d), "date": d})
    return days


def schedule_buildings(event: Event) -> list[str]:
    return list(
        event.schedule_items.exclude(building="")
        .values_list("building", flat=True).distinct().order_by("building")
    )


def schedule_rooms(event: Event, building: str | None = None) -> list[dict]:
    """Distinct (room_name, room_number) pairs from schedule items."""
    qs = event.schedule_items.all()
    if building:
        qs = qs.filter(building=building)
    pairs = qs.values_list("room_name", "room_number").distinct().order_by("room_name", "room_number")
    return [
        {"room_name": name, "room_number": number,
         "label": f"{name} ({number})" if name and number else (name or number)}
        for name, number in pairs
        if name or number
    ]


def filter_schedule(
    event: Event,
    building: str = "",
    room_number: str = "",
    day: str = "",
    av: str = "",
    search: str = "",
):
    qs = event.schedule_items.all()
    if building:
        qs = qs.filter(building=building)
    if room_number:
        qs = qs.filter(room_number=room_number)
    if day:
        d = date.fromisoformat(day)
        start, end = day_bounds(event, d)
        qs = qs.filter(starts_at__gte=start, starts_at__lt=end)
    if av == "yes":
        qs = qs.filter(has_av=True)
    elif av == "no":
        qs = qs.filter(has_av=False)
    if search:
        from django.db.models import Q
        qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))
    return qs


def shifts_on(event: Event, d: date):
    start, end = day_bounds(event, d)
    return event.staff_shifts.filter(starts_at__gte=start, starts_at__lt=end)
