import math

from django.shortcuts import render

from accounts.roles import MANAGER, require_role
from ..selectors import schedule_days
from ..shortcuts import get_event_or_404
from ..timeutil import minutes_since_midnight

HEAT_START_MIN = 8 * 60      # 8:00 AM
HEAT_END_MIN = 26 * 60       # 2:00 AM next day
SLOT_MINUTES = 30
HEAT_LEVELS = 5


def _fmt_hour(minutes: int) -> str:
    h = (minutes // 60) % 24
    ampm = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12} {ampm}"


def _fmt_time(minutes: int) -> str:
    h = (minutes // 60) % 24
    ampm = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{minutes % 60:02d} {ampm}"


@require_role(MANAGER)
def analytics(request, slug):
    event = get_event_or_404(slug)
    tz = event.tz

    items = list(event.schedule_items.all())
    active = [i for i in items if not i.is_cancelled]
    av_items = [i for i in active if i.has_av]

    def duration_hours(item):
        return (item.ends_at - item.starts_at).total_seconds() / 3600

    days = schedule_days(event)

    # --- KPIs ---
    av_by_day = {}
    for item in av_items:
        d = item.starts_at.astimezone(tz).date()
        av_by_day[d] = av_by_day.get(d, 0) + 1
    busiest = max(av_by_day.items(), key=lambda kv: kv[1]) if av_by_day else None

    kpis = {
        "total_panels": len(active),
        "av_panels": len(av_items),
        "av_hours": round(sum(duration_hours(i) for i in av_items), 1),
        "av_rooms": len({(i.building, i.room_name, i.room_number) for i in av_items}),
        "cancelled": len(items) - len(active),
        "busiest_day": busiest[0].strftime("%A (%-m/%-d)") if busiest else "—",
        "busiest_count": busiest[1] if busiest else 0,
    }

    # --- AV panel-hours per room (top 15, horizontal bars) ---
    per_room = {}
    for item in av_items:
        key = item.room_label or item.building
        agg = per_room.setdefault(key, {"label": key, "building": item.building, "count": 0, "hours": 0.0})
        agg["count"] += 1
        agg["hours"] += duration_hours(item)
    rooms_ranked = sorted(per_room.values(), key=lambda r: -r["hours"])
    top_rooms = rooms_ranked[:15]
    others = len(rooms_ranked) - len(top_rooms)
    max_hours = max((r["hours"] for r in top_rooms), default=1)
    for r in top_rooms:
        r["hours"] = round(r["hours"], 1)
        r["pct"] = round(r["hours"] / max_hours * 100, 1)

    # --- AV load heatmap: day rows x half-hour columns ---
    slots = list(range(HEAT_START_MIN, HEAT_END_MIN, SLOT_MINUTES))
    heat_rows = []
    heat_max = 0
    for d in days:
        day = d["date"]
        day_av = [
            (minutes_since_midnight(i.starts_at, day, tz), minutes_since_midnight(i.ends_at, day, tz))
            for i in av_items
            if i.starts_at.astimezone(tz).date() == day
        ]
        cells = []
        for m in slots:
            count = sum(1 for start, end in day_av if start < m + SLOT_MINUTES and end > m)
            heat_max = max(heat_max, count)
            cells.append({"count": count, "minute": m})
        heat_rows.append({"label": d["label"], "cells": cells})

    for row in heat_rows:
        for cell in row["cells"]:
            cell["level"] = math.ceil(cell["count"] / heat_max * HEAT_LEVELS) if cell["count"] else 0
            cell["tip"] = (
                f"{row['label']} {_fmt_time(cell['minute'])} — "
                f"{cell['count']} AV panel{'s' if cell['count'] != 1 else ''}"
            )

    hour_row = [_fmt_hour(m) if m % 120 == 0 else "" for m in slots]

    return render(request, "analytics.html", {
        "event": event,
        "kpis": kpis,
        "top_rooms": top_rooms,
        "others_count": others,
        "heat_rows": heat_rows,
        "heat_max": heat_max,
        "hour_row": hour_row,
    })
