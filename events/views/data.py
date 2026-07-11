"""Custom data-editing pages under Manage — replaces the Django admin for
per-event rooms/equipment/checklists, schedule items, and staff shifts."""
from datetime import date

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.roles import MANAGER, require_role
from ..audit import audit
from ..forms import ChecklistFormSet, EquipmentFormSet, RoomForm, ScheduleItemForm, StaffShiftForm
from ..models import Room, ScheduleItem, StaffShift
from ..selectors import day_bounds, schedule_buildings, schedule_days
from ..shortcuts import get_event_or_404


# ---------- Rooms (with equipment + checklist inlines) ----------

@require_role(MANAGER)
def rooms_list(request, slug):
    event = get_event_or_404(slug)
    return render(request, "manage/data_rooms.html", {"event": event, "rooms": event.rooms.all()})


@require_role(MANAGER)
def room_edit(request, slug, room_id=None):
    event = get_event_or_404(slug)
    room = get_object_or_404(Room, pk=room_id, event=event) if room_id else None

    if request.method == "POST":
        form = RoomForm(request.POST, instance=room)
        equipment = EquipmentFormSet(request.POST, instance=room, prefix="eq")
        checklist = ChecklistFormSet(request.POST, instance=room, prefix="cl")
        if form.is_valid() and (room is None or (equipment.is_valid() and checklist.is_valid())):
            new_room = form.save(commit=False)
            new_room.event = event
            new_room.save()
            if room is not None:
                equipment.save()
                checklist.save()
            audit(event, request.user, "data", f"{'Updated' if room else 'Created'} room {new_room}")
            messages.success(request, f"Room saved. {'' if room else 'Add equipment and checklist items below.'}")
            return redirect("events:data_room_edit", slug=slug, room_id=new_room.pk)
    else:
        form = RoomForm(instance=room)
        equipment = EquipmentFormSet(instance=room, prefix="eq")
        checklist = ChecklistFormSet(instance=room, prefix="cl")

    return render(request, "manage/data_room_form.html", {
        "event": event, "room": room, "form": form,
        "equipment_formset": equipment if room else None,
        "checklist_formset": checklist if room else None,
    })


@require_role(MANAGER)
@require_POST
def room_delete(request, slug, room_id):
    event = get_event_or_404(slug)
    room = get_object_or_404(Room, pk=room_id, event=event)
    audit(event, request.user, "data", f"Deleted room {room}")
    room.delete()
    messages.success(request, "Room deleted.")
    return redirect("events:data_rooms", slug=slug)


# ---------- Schedule items ----------

@require_role(MANAGER)
def schedule_list(request, slug):
    event = get_event_or_404(slug)
    qs = event.schedule_items.all()
    building = request.GET.get("building", "")
    day = request.GET.get("day", "")
    search = request.GET.get("search", "")
    if building:
        qs = qs.filter(building=building)
    if day:
        try:
            start, end = day_bounds(event, date.fromisoformat(day))
            qs = qs.filter(starts_at__gte=start, starts_at__lt=end)
        except ValueError:
            pass
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(request, "manage/data_schedule.html", {
        "event": event, "page": page,
        "buildings": schedule_buildings(event), "days": schedule_days(event),
        "selected_building": building, "selected_day": day, "selected_search": search,
    })


@require_role(MANAGER)
def schedule_edit(request, slug, item_id=None):
    event = get_event_or_404(slug)
    item = get_object_or_404(ScheduleItem, pk=item_id, event=event) if item_id else None
    if request.method == "POST":
        form = ScheduleItemForm(request.POST, instance=item)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.event = event
            obj.room = event.rooms.filter(building=obj.building, room_number=obj.room_number).first()
            obj.save()
            audit(event, request.user, "data", f"{'Updated' if item else 'Created'} schedule item '{obj.title}'")
            messages.success(request, "Schedule item saved.")
            return redirect("events:data_schedule", slug=slug)
    else:
        form = ScheduleItemForm(instance=item)
    return render(request, "manage/data_form.html", {
        "event": event, "form": form,
        "title": "Edit Schedule Item" if item else "New Schedule Item",
        "back_url_name": "events:data_schedule",
    })


@require_role(MANAGER)
@require_POST
def schedule_delete(request, slug, item_id):
    event = get_event_or_404(slug)
    item = get_object_or_404(ScheduleItem, pk=item_id, event=event)
    audit(event, request.user, "data", f"Deleted schedule item '{item.title}'")
    item.delete()
    messages.success(request, "Schedule item deleted.")
    return redirect("events:data_schedule", slug=slug)


# ---------- Staff shifts ----------

@require_role(MANAGER)
def shifts_list(request, slug):
    event = get_event_or_404(slug)
    page = Paginator(event.staff_shifts.all(), 50).get_page(request.GET.get("page"))
    return render(request, "manage/data_shifts.html", {"event": event, "page": page})


@require_role(MANAGER)
def shift_edit(request, slug, shift_id=None):
    event = get_event_or_404(slug)
    shift = get_object_or_404(StaffShift, pk=shift_id, event=event) if shift_id else None
    if request.method == "POST":
        form = StaffShiftForm(request.POST, instance=shift)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.event = event
            obj.save()
            audit(event, request.user, "data", f"{'Updated' if shift else 'Created'} shift for {obj.staff_name}")
            messages.success(request, "Shift saved.")
            return redirect("events:data_shifts", slug=slug)
    else:
        form = StaffShiftForm(instance=shift)
    return render(request, "manage/data_form.html", {
        "event": event, "form": form,
        "title": "Edit Staff Shift" if shift else "New Staff Shift",
        "back_url_name": "events:data_shifts",
    })


@require_role(MANAGER)
@require_POST
def shift_delete(request, slug, shift_id):
    event = get_event_or_404(slug)
    shift = get_object_or_404(StaffShift, pk=shift_id, event=event)
    audit(event, request.user, "data", f"Deleted shift for {shift.staff_name}")
    shift.delete()
    messages.success(request, "Shift deleted.")
    return redirect("events:data_shifts", slug=slug)
