import threading

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.roles import STAFF, VIEWER, require_role
from ..audit import audit
from ..models import ChecklistItem, Room
from ..shortcuts import get_event_or_404

STATUS_META = {
    "": {"label": "Not started", "color": "#4b5563"},
    "in_progress": {"label": "In progress", "color": "#b45309"},
    "ready": {"label": "Ready", "color": "#15803d"},
    "issue": {"label": "Issue", "color": "#b91c1c"},
}


@require_role(VIEWER)
def rooms_page(request, slug):
    event = get_event_or_404(slug)
    buildings = {}
    for room in event.rooms.all():
        buildings.setdefault(room.building, []).append(room)
    return render(request, "rooms.html", {"event": event, "buildings": buildings})


@require_role(VIEWER)
def room_detail(request, slug, room_id):
    event = get_event_or_404(slug)
    room = get_object_or_404(Room, pk=room_id, event=event)

    equipment_by_type = {}
    for item in room.equipment.all():
        equipment_by_type.setdefault(item.equipment_type or "Other", []).append(item)

    # Match by FK or by denormalized building+room_number (sheet rows may not resolve)
    items = event.schedule_items.filter(
        Q(room=room) | Q(building=room.building, room_number=room.room_number)
    ).distinct()

    checklist = room.checklist_items.all()

    return render(request, "partials/room_detail.html", {
        "event": event,
        "room": room,
        "equipment_by_type": equipment_by_type,
        "items": items,
        "checklist": checklist,
        "status_choices": Room.STATUS_CHOICES,
        "can_check": request.user.is_superuser or request.user.groups.filter(
            name__in=["Staff", "Manager", "Admin"]).exists(),
    })


@require_role(STAFF)
@require_POST
def toggle_checklist(request, slug, item_id):
    event = get_event_or_404(slug)
    item = get_object_or_404(ChecklistItem, pk=item_id, room__event=event)

    checked = request.POST.get("checked") == "1"
    item.checked = checked
    if checked:
        item.checked_by = request.POST.get("checked_by", "") or request.user.get_username()
        item.checked_at = timezone.now()
    else:
        item.checked_by = ""
        item.checked_at = None
    item.save(update_fields=["checked", "checked_by", "checked_at"])
    audit(event, request.user, "checklist",
          f"{'Checked' if checked else 'Unchecked'} '{item.item}' in {item.room}")

    if event.sheets_enabled and event.checklist_tab:
        from sync.checklist_writeback import write_checklist_for_event
        threading.Thread(target=write_checklist_for_event, args=(event.pk,), daemon=True).start()

    return HttpResponse(status=204)


@require_role(STAFF)
def status_board(request, slug):
    event = get_event_or_404(slug)
    buildings = {}
    counts = {key: 0 for key in STATUS_META}
    for room in event.rooms.all():
        room.status_meta = STATUS_META.get(room.setup_status, STATUS_META[""])
        buildings.setdefault(room.building, []).append(room)
        counts[room.setup_status if room.setup_status in counts else ""] += 1

    summary = [
        {"key": key, "label": meta["label"], "color": meta["color"], "count": counts[key]}
        for key, meta in STATUS_META.items()
    ]
    return render(request, "status_board.html", {
        "event": event,
        "buildings": buildings,
        "summary": summary,
        "total": sum(counts.values()),
    })


@require_role(STAFF)
@require_POST
def set_room_status(request, slug, room_id):
    event = get_event_or_404(slug)
    room = get_object_or_404(Room, pk=room_id, event=event)

    status = request.POST.get("status", "")
    if status not in STATUS_META:
        return HttpResponse("Invalid status", status=400)

    room.setup_status = status
    room.status_note = request.POST.get("note", "").strip()[:300]
    room.status_updated_by = request.user.get_username()
    room.status_updated_at = timezone.now()
    room.save(update_fields=["setup_status", "status_note", "status_updated_by", "status_updated_at"])
    audit(event, request.user, "room_status",
          f"{room}: {STATUS_META[status]['label']}" + (f" — {room.status_note}" if room.status_note else ""))

    return HttpResponse(status=204)
