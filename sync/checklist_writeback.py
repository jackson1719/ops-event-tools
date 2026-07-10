"""Write the current checklist state back to the event's Google Sheet."""
import logging

from django.db import connection

from events.models import ChecklistItem, Event

from .sheets import get_client, get_worksheet

log = logging.getLogger(__name__)


def write_checklist_for_event(event_pk: int) -> None:
    try:
        event = Event.objects.get(pk=event_pk)
        if not (event.sheets_enabled and event.checklist_tab):
            return
        items = (
            ChecklistItem.objects.filter(room__event=event)
            .select_related("room")
            .order_by("room__building", "room__room_number", "position")
        )
        rows = [["building", "room_name", "room_number", "item", "checked", "checked_by", "checked_at"]]
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
        ws.clear()
        ws.update(rows, "A1")
        log.info("Checklist written to sheet for %s (%d items)", event.slug, len(rows) - 1)
    except Exception:
        log.exception("Checklist write-back failed")
    finally:
        connection.close()
