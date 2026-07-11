"""Per-event sync: fetch sheets, parse once, replace/upsert in one transaction."""
import logging
import re
from datetime import datetime, timedelta

from django.db import connection, transaction
from django.utils import timezone

from events.models import ChecklistItem, Equipment, Event, Room, ScheduleChange, ScheduleItem, StaffShift
from events.timeutil import parse_sheet_date, parse_time_range

from .schedule_diff import diff_schedules
from .sheets import fetch_event_sheets

CHANGE_RETENTION_DAYS = 14

log = logging.getLogger(__name__)

RUNNING_STALE_AFTER = timedelta(minutes=5)

CANCELLED_PREFIX = re.compile(r"^\s*cancell?ed[:\s\-]+", re.IGNORECASE)


def split_cancelled(title: str) -> tuple[str, bool]:
    """'CANCELLED Just Dance!' -> ('Just Dance!', True)."""
    m = CANCELLED_PREFIX.match(title)
    if not m:
        return title, False
    stripped = title[m.end():].strip()
    return (stripped or title, True)


def sync_event(event: Event) -> None:
    """Sync one event from its spreadsheet. Raises on fetch errors; records
    status on the Event row either way."""
    if not event.sheets_enabled:
        log.info("Event %s has no spreadsheet configured; skipping.", event.slug)
        return

    # Cross-process running guard
    event.refresh_from_db()
    if (
        event.last_sync_status == "running"
        and event.last_sync_at
        and timezone.now() - event.last_sync_at < RUNNING_STALE_AFTER
    ):
        log.info("Sync already running for %s; skipping.", event.slug)
        return

    Event.objects.filter(pk=event.pk).update(last_sync_at=timezone.now(), last_sync_status="running")

    try:
        data = fetch_event_sheets(event)
        warnings = _apply(event, data)
        Event.objects.filter(pk=event.pk).update(
            last_sync_at=timezone.now(),
            last_sync_status="success",
            last_sync_error="\n".join(warnings),
        )
        log.info(
            "Sync complete for %s: %d rooms, %d equipment, %d schedule items, %d staff shifts (%d warnings)",
            event.slug, len(data["rooms"]), len(data["equipment"]),
            len(data["schedule"]), len(data["staff"]), len(warnings),
        )
    except Exception as exc:
        Event.objects.filter(pk=event.pk).update(
            last_sync_at=timezone.now(),
            last_sync_status="error",
            last_sync_error=f"{type(exc).__name__}: {exc}",
        )
        log.error("Sync failed for %s: %s", event.slug, exc)
        raise


@transaction.atomic
def _apply(event: Event, data: dict) -> list[str]:
    warnings: list[str] = []
    tz = event.tz

    # --- Rooms: upsert (rooms carry user data: images, checklist state) ---
    seen_keys = set()
    for row in data["rooms"]:
        key = (row["building"], row["room_number"])
        seen_keys.add(key)
        Room.objects.update_or_create(
            event=event,
            building=row["building"],
            room_number=row["room_number"],
            defaults={"name": row["name"], "floor": row["floor"]},
        )
    for room in event.rooms.all():
        if (room.building, room.room_number) in seen_keys:
            continue
        has_user_data = (
            bool(room.layout_image)
            or bool(room.setup_status)
            or room.checklist_items.filter(checked=True).exists()
        )
        if has_user_data:
            warnings.append(
                f"Room '{room}' removed from sheet but kept (has image or checked checklist items)."
            )
        else:
            room.delete()

    rooms_by_key = {(r.building, r.room_number): r for r in event.rooms.all()}

    # --- Equipment: replace ---
    Equipment.objects.filter(room__event=event).delete()
    equipment_objs = []
    for row in data["equipment"]:
        room = rooms_by_key.get((row["building"], row["room_number"]))
        if room is None:
            warnings.append(
                f"Equipment '{row['item_name']}' references unknown room "
                f"{row['building']}/{row['room_number']}; skipped."
            )
            continue
        equipment_objs.append(Equipment(
            room=room,
            vendor=row["vendor"],
            equipment_type=row["equipment_type"],
            quantity=row["quantity"],
            item_name=row["item_name"],
        ))
    Equipment.objects.bulk_create(equipment_objs)

    # --- Schedule items: replace (snapshot first for change tracking) ---
    old_schedule = list(event.schedule_items.values(
        "title", "room_name", "room_number", "building",
        "starts_at", "ends_at", "is_cancelled", "has_av",
    ))
    event.schedule_items.all().delete()
    schedule_objs = []
    for row in data["schedule"]:
        d = parse_sheet_date(row["date"])
        parsed = parse_time_range(d, row["start_time"], row["end_time"], tz) if d else None
        if parsed is None:
            warnings.append(
                f"Schedule row '{row['title']}' has unparseable date/time "
                f"({row['date']} {row['start_time']}-{row['end_time']}); skipped."
            )
            continue
        starts_at, ends_at = parsed
        title, is_cancelled = split_cancelled(row["title"])
        schedule_objs.append(ScheduleItem(
            event=event,
            room=rooms_by_key.get((row["building"], row["room_number"])),
            building=row["building"],
            room_name=row["room_name"],
            room_number=row["room_number"],
            title=title,
            description=row["description"],
            has_av=row["av"].lower() == "yes",
            is_cancelled=is_cancelled,
            starts_at=starts_at,
            ends_at=ends_at,
        ))
    ScheduleItem.objects.bulk_create(schedule_objs)

    # --- Change tracking (skipped on the first sync — everything would be "added") ---
    if old_schedule:
        changes = diff_schedules(event, old_schedule, schedule_objs, timezone.now())
        ScheduleChange.objects.bulk_create(changes)
        if changes:
            log.info("Schedule changes detected for %s: %d", event.slug, len(changes))
    ScheduleChange.objects.filter(
        event=event,
        synced_at__lt=timezone.now() - timedelta(days=CHANGE_RETENTION_DAYS),
    ).delete()

    # --- Staff shifts: replace ---
    event.staff_shifts.all().delete()
    shift_objs = []
    for row in data["staff"]:
        d = parse_sheet_date(row["date"])
        parsed = parse_time_range(d, row["start_time"], row["end_time"], tz) if d else None
        if parsed is None:
            warnings.append(
                f"Staff shift for '{row['staff_name']}' has unparseable date/time; skipped."
            )
            continue
        starts_at, ends_at = parsed
        shift_objs.append(StaffShift(
            event=event,
            staff_name=row["staff_name"],
            starts_at=starts_at,
            ends_at=ends_at,
            notes=row["notes"],
        ))
    StaffShift.objects.bulk_create(shift_objs)

    # --- Checklist: replace from sheet (sheet is authoritative; toggles write back) ---
    if data["checklist"] is not None:
        ChecklistItem.objects.filter(room__event=event).delete()
        checklist_objs = []
        for i, row in enumerate(data["checklist"]):
            room = rooms_by_key.get((row["building"], row["room_number"]))
            if room is None:
                warnings.append(
                    f"Checklist item '{row['item']}' references unknown room "
                    f"{row['building']}/{row['room_number']}; skipped."
                )
                continue
            checked_at = None
            if row["checked"] and row["checked_at"]:
                try:
                    checked_at = datetime.fromisoformat(row["checked_at"])
                    if checked_at.tzinfo is None:
                        checked_at = checked_at.replace(tzinfo=tz)
                except ValueError:
                    pass
            checklist_objs.append(ChecklistItem(
                room=room,
                item=row["item"],
                position=i,
                checked=row["checked"],
                checked_by=row["checked_by"],
                checked_at=checked_at,
            ))
        ChecklistItem.objects.bulk_create(checklist_objs)

    return warnings


def sync_event_in_thread(event_pk: int) -> None:
    """Entry point for the manual-trigger background thread."""
    try:
        event = Event.objects.get(pk=event_pk)
        sync_event(event)
    except Exception:
        log.exception("Background sync failed")
    finally:
        connection.close()
