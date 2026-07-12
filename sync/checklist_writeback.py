"""Write the current checklist state back to the event's Google Sheet."""
import logging

from django.db import connection

from events.models import ChecklistItem, Event

from .locks import Locked, exclusive
from .sheets import get_client, get_worksheet

log = logging.getLogger(__name__)

HEADER = ["building", "room_name", "room_number", "item", "checked", "checked_by", "checked_at"]


def write_checklist_for_event(event_pk: int) -> None:
    try:
        event = Event.objects.get(pk=event_pk)
        if not (event.sheets_enabled and event.checklist_tab):
            return
        # Serialize write-backs per event so rapid toggles can't interleave and
        # leave the sheet holding stale state (blocking: last write wins).
        with exclusive(f"checklist-{event_pk}", blocking=True):
            _write(event)
    except Exception:
        log.exception("Checklist write-back failed")
    finally:
        connection.close()


def _write(event: Event) -> None:
    items = (
        ChecklistItem.objects.filter(room__event=event)
        .select_related("room")
        .order_by("room__building", "room__room_number", "position")
    )
    rows = [HEADER]
    for item in items:
        rows.append([
            item.room.building,
            item.room.name,
            item.room.room_number,
            item.item,
            "Yes" if item.checked else "",
            item.checked_by,
            item.checked_at.astimezone(event.tz).isoformat() if item.checked_at else "",
        ])
    client = get_client()
    ws = get_worksheet(client, event.spreadsheet_id, event.checklist_tab)
    # Single update over a padded range (no clear()+update() gap that a
    # concurrent sync could read as an empty tab and treat as authoritative).
    blanks = [["", "", "", "", "", "", ""]]
    padded = rows + blanks * 50
    ws.update(padded, f"A1:G{len(padded)}")
    log.info("Checklist written to sheet for %s (%d items)", event.slug, len(rows) - 1)
