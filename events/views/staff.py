from datetime import date, time, timedelta, timezone as dt_timezone

from django.contrib.auth.decorators import login_not_required
from django.http import Http404, HttpResponse
from django.shortcuts import render

from accounts.roles import STAFF, require_role
from ..selectors import fmt_time, shifts_on, staff_days
from ..shortcuts import get_event_or_404
from ..timeutil import combine_aware, event_now, minutes_since_midnight, parse_sheet_time


def _distinct_staff(event):
    return list(
        event.staff_shifts.values_list("staff_name", flat=True).distinct().order_by("staff_name")
    )


@require_role(STAFF)
def staff_page(request, slug):
    event = get_event_or_404(slug)
    return render(request, "staff.html", {
        "event": event,
        "days": staff_days(event),
        "staff_names": _distinct_staff(event),
        "selected_view": request.GET.get("view", "table"),
    })


@require_role(STAFF)
def staff_table(request, slug):
    event = get_event_or_404(slug)
    qs = event.staff_shifts.all()
    staff_name = request.GET.get("staff", "").strip()
    day = request.GET.get("day", "").strip()
    if staff_name:
        qs = qs.filter(staff_name=staff_name)
    if day:
        try:
            qs = shifts_on(event, date.fromisoformat(day)).filter(
                staff_name=staff_name) if staff_name else shifts_on(event, date.fromisoformat(day))
        except ValueError:
            pass
    return render(request, "partials/staff_table.html", {"event": event, "shifts": qs})


@require_role(STAFF)
def staff_on_shift(request, slug):
    event = get_event_or_404(slug)
    now = event_now(event)

    test_day = request.GET.get("day", "").strip()
    test_time = request.GET.get("time", "").strip()
    if test_day:
        try:
            d = date.fromisoformat(test_day)
            now = combine_aware(d, now.timetz().replace(tzinfo=None), event.tz)
        except ValueError:
            pass
    if test_time:
        t = parse_sheet_time(test_time)
        if t is not None:
            now = combine_aware(now.date(), t, event.tz)

    shifts = event.staff_shifts.filter(starts_at__lte=now, ends_at__gte=now)
    return render(request, "partials/staff_on_shift.html", {"event": event, "shifts": shifts, "now": now})


@require_role(STAFF)
def staff_timeline(request, slug):
    event = get_event_or_404(slug)
    days = staff_days(event)
    day_param = request.GET.get("day", "").strip()
    d = None
    if day_param:
        try:
            d = date.fromisoformat(day_param)
        except ValueError:
            pass
    if d is None:
        d = days[0]["date"] if days else event_now(event).date()

    tz = event.tz
    shifts_data = [
        {
            "staff_name": s.staff_name,
            "start_min": minutes_since_midnight(s.starts_at, d, tz),
            "end_min": minutes_since_midnight(s.ends_at, d, tz),
            "start_time": fmt_time(s.starts_at, tz),
            "end_time": fmt_time(s.ends_at, tz),
            "notes": s.notes,
        }
        for s in shifts_on(event, d)
    ]
    return render(request, "partials/staff_timeline.html", {
        "event": event,
        "shifts_data": shifts_data,
        "day": d,
    })


@require_role(STAFF)
def staff_heatmap(request, slug):
    event = get_event_or_404(slug)
    days = staff_days(event)
    day_param = request.GET.get("day", "").strip()
    d = None
    if day_param:
        try:
            d = date.fromisoformat(day_param)
        except ValueError:
            pass
    if d is None:
        d = days[0]["date"] if days else event_now(event).date()

    shifts = list(shifts_on(event, d))
    tz = event.tz
    buckets = []
    for m in range(360, 1440, 30):
        slot_start = combine_aware(d, time(m // 60, m % 60), tz)
        slot_end = slot_start + timedelta(minutes=30)
        count = sum(1 for s in shifts if s.starts_at < slot_end and s.ends_at > slot_start)
        h = m // 60
        mins = m % 60
        ampm = "AM" if h < 12 else "PM"
        h12 = h if h <= 12 else h - 12
        if h12 == 0:
            h12 = 12
        buckets.append({"label": f"{h12}:{mins:02d} {ampm}", "count": count})
    return render(request, "partials/staff_heatmap.html", {"event": event, "buckets": buckets, "day": d})


@require_role(STAFF)
def staff_directory(request, slug):
    event = get_event_or_404(slug)
    name = request.GET.get("staff", "").strip()
    shifts = event.staff_shifts.filter(staff_name=name) if name else []
    return render(request, "partials/staff_directory.html", {
        "event": event,
        "shifts": shifts,
        "selected_staff": name,
        "staff_names": _distinct_staff(event),
    })


@require_role(STAFF)
def staff_mine(request, slug):
    event = get_event_or_404(slug)
    staff_name = request.user.staff_name
    shifts = event.staff_shifts.filter(staff_name=staff_name) if staff_name else []
    ics_url = None
    if staff_name:
        token = request.user.get_or_create_ical_token()
        ics_url = request.build_absolute_uri(
            f"/e/{event.slug}/staff/my.ics?token={token}"
        )
    return render(request, "partials/staff_mine.html", {
        "event": event,
        "shifts": shifts,
        "staff_name": staff_name,
        "ics_url": ics_url,
    })


def _ics_escape(value: str) -> str:
    # Normalize all newline forms first so a stray CR can't inject a raw line
    # into the CRLF-delimited feed, then escape per RFC 5545.
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return (
        value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    )


@login_not_required
def my_shifts_ics(request, slug):
    """Token-authenticated iCal feed — calendar apps can't do session login."""
    from accounts.models import User

    event = get_event_or_404(slug)
    token = request.GET.get("token", "")
    user = User.objects.filter(ical_token=token).first() if token else None
    if user is None or not user.staff_name:
        raise Http404

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ops-event-tools//EN",
        f"X-WR-CALNAME:{_ics_escape(event.name)} AV Shifts",
    ]
    for shift in event.staff_shifts.filter(staff_name=user.staff_name):
        starts = shift.starts_at.astimezone(dt_timezone.utc)
        ends = shift.ends_at.astimezone(dt_timezone.utc)
        lines += [
            "BEGIN:VEVENT",
            f"UID:shift-{shift.pk}@ops-event-tools",
            f"DTSTART:{starts.strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{ends.strftime('%Y%m%dT%H%M%SZ')}",
            f"SUMMARY:{_ics_escape(f'AV Shift — {event.name}')}",
        ]
        if shift.notes:
            lines.append(f"DESCRIPTION:{_ics_escape(shift.notes)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")

    return HttpResponse("\r\n".join(lines), content_type="text/calendar")


@require_role(STAFF)
def staff_print(request, slug):
    event = get_event_or_404(slug)
    day = request.GET.get("day", "").strip()
    if day:
        try:
            qs = shifts_on(event, date.fromisoformat(day))
        except ValueError:
            qs = event.staff_shifts.all()
    else:
        qs = event.staff_shifts.all()

    tz = event.tz
    days_grouped = {}
    for s in qs:
        d = s.starts_at.astimezone(tz).date()
        days_grouped.setdefault(d, []).append(s)

    return render(request, "staff_print.html", {
        "event": event,
        "days_grouped": days_grouped,
        "total": qs.count(),
    })
