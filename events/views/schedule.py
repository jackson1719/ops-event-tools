from django.shortcuts import render

from accounts.roles import VIEWER, require_role
from ..selectors import (
    filter_schedule,
    format_day,
    schedule_buildings,
    schedule_days,
    schedule_rooms as distinct_rooms,
)
from ..shortcuts import get_event_or_404
from ..timeutil import event_today


@require_role(VIEWER)
def schedule_page(request, slug):
    event = get_event_or_404(slug)
    buildings = schedule_buildings(event)
    days = schedule_days(event)
    building = request.GET.get("building", "")
    room_number = request.GET.get("room_number", "")
    day = request.GET.get("day", "")
    search = request.GET.get("search", "")
    rooms = distinct_rooms(event, building or None)

    # Default to today if no filters set and today has items
    if not building and not room_number and not day and not search:
        today_iso = event_today(event).isoformat()
        if any(d["value"] == today_iso for d in days):
            day = today_iso

    return render(request, "schedule.html", {
        "event": event,
        "buildings": buildings,
        "days": days,
        "rooms": rooms,
        "selected_building": building,
        "selected_room_number": room_number,
        "selected_day": day,
        "selected_search": search,
    })


@require_role(VIEWER)
def schedule_table(request, slug):
    event = get_event_or_404(slug)
    items = filter_schedule(
        event,
        building=request.GET.get("building", "").strip(),
        room_number=request.GET.get("room_number", "").strip(),
        day=request.GET.get("day", "").strip(),
        av=request.GET.get("av", "").strip(),
        search=request.GET.get("search", "").strip(),
    )
    return render(request, "partials/schedule_table.html", {"event": event, "items": items})


@require_role(VIEWER)
def schedule_rooms(request, slug):
    event = get_event_or_404(slug)
    building = request.GET.get("building", "").strip()
    rooms = distinct_rooms(event, building or None)
    return render(request, "partials/room_options.html", {
        "rooms": rooms,
        "selected_room_number": request.GET.get("room_number", ""),
    })


@require_role(VIEWER)
def schedule_print(request, slug):
    event = get_event_or_404(slug)
    building = request.GET.get("building", "").strip()
    room_number = request.GET.get("room_number", "").strip()
    day = request.GET.get("day", "").strip()
    av = request.GET.get("av", "").strip()
    search = request.GET.get("search", "").strip()

    items = filter_schedule(event, building=building, room_number=room_number, day=day, av=av, search=search)

    tz = event.tz
    days_grouped = {}
    for item in items:
        d = item.starts_at.astimezone(tz).date()
        days_grouped.setdefault(d, []).append(item)

    filters = []
    if building:
        filters.append(f"Building: {building}")
    if room_number:
        filters.append(f"Room: {room_number}")
    if day:
        from datetime import date
        filters.append(f"Day: {format_day(date.fromisoformat(day))}")
    if av:
        filters.append(f"AV: {av}")
    if search:
        filters.append(f"Search: {search}")

    return render(request, "schedule_print.html", {
        "event": event,
        "days_grouped": days_grouped,
        "filters": filters,
        "total": len(items),
    })
