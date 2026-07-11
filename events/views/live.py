from datetime import date

from django.shortcuts import render

from accounts.roles import VIEWER, require_role
from ..selectors import fmt_time, schedule_buildings, schedule_days, day_bounds
from ..shortcuts import get_event_or_404
from ..timeutil import event_today, minutes_since_midnight, parse_sheet_time


@require_role(VIEWER)
def live_page(request, slug):
    event = get_event_or_404(slug)

    buildings = schedule_buildings(event)
    days = schedule_days(event)

    default_building = "Summit" if "Summit" in buildings else (buildings[0] if buildings else "")
    building = request.GET.get("building", default_building)
    av = request.GET.get("av", "yes")
    test_date = request.GET.get("date", "")
    test_time = request.GET.get("time", "")

    # Display date: test date (ISO) or today in event tz
    display_date = event_today(event)
    if test_date:
        try:
            display_date = date.fromisoformat(test_date)
        except ValueError:
            pass

    # Test "now" in minutes for the JS (from <input type=time>, HH:MM)
    test_now_minutes = None
    if test_time:
        t = parse_sheet_time(test_time)
        if t is not None:
            test_now_minutes = t.hour * 60 + t.minute

    start, end = day_bounds(event, display_date)
    qs = event.schedule_items.filter(starts_at__gte=start, starts_at__lt=end)
    if building:
        qs = qs.filter(building=building)
    if av == "yes":
        qs = qs.filter(has_av=True)
    elif av == "no":
        qs = qs.filter(has_av=False)

    tz = event.tz
    events_data = [
        {
            "event_name": item.title,
            "room_name": item.room_name,
            "room_number": item.room_number,
            "building": item.building,
            "av": "Yes" if item.has_av else "No",
            "cancelled": item.is_cancelled,
            "start_min": minutes_since_midnight(item.starts_at, display_date, tz),
            "end_min": minutes_since_midnight(item.ends_at, display_date, tz),
            "start_time": fmt_time(item.starts_at, tz),
            "end_time": fmt_time(item.ends_at, tz),
            "description": item.description,
        }
        for item in qs
    ]

    return render(request, "live.html", {
        "event": event,
        "events_data": events_data,
        "test_now_minutes": test_now_minutes,
        "buildings": buildings,
        "days": days,
        "selected_building": building,
        "selected_av": av,
        "selected_date": test_date,
        "selected_time": test_time,
    })
