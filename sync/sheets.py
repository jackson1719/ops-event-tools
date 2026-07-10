"""Google Sheets fetching for an event. Raw fetch + row transformation only;
parsing into model-ready values happens in engine.py."""
import gspread
from django.conf import settings
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_client() -> gspread.Client:
    creds = Credentials.from_service_account_file(settings.GOOGLE_CREDENTIALS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def get_worksheet(client: gspread.Client, spreadsheet_id: str, tab: str) -> gspread.Worksheet:
    return client.open_by_key(spreadsheet_id).worksheet(tab)


def fetch_event_sheets(event) -> dict[str, list[dict] | None]:
    """Fetch all configured tabs for an event as lists of raw string dicts.

    Tab column contracts (unchanged from the old app):
      Rooms:      building, floor, room_name, room_number
      Equipment:  building, room_name, room_number, vendor, type, qty, equipment
      Events:     date, start_time, end_time, building, room_name, room_number, av, name, desc
      Staff:      staff, date, day, start_time, end_time, notes
      Checklist:  building, room_name, room_number, item, checked, checked_by, checked_at
    """
    client = get_client()
    sid = event.spreadsheet_id
    data: dict[str, list[dict] | None] = {}

    raw = get_worksheet(client, sid, event.rooms_tab).get_all_records()
    data["rooms"] = [
        {
            "name": str(row.get("room_name", "")).strip(),
            "room_number": str(row.get("room_number", "")).strip(),
            "building": str(row.get("building", "")).strip(),
            "floor": str(row.get("floor", "")).strip(),
        }
        for row in raw
        if str(row.get("room_name", "")).strip()
    ]

    raw = get_worksheet(client, sid, event.equipment_tab).get_all_records()
    data["equipment"] = [
        {
            "building": str(row.get("building", "")).strip(),
            "room_name": str(row.get("room_name", "")).strip(),
            "room_number": str(row.get("room_number", "")).strip(),
            "vendor": str(row.get("vendor", "")).strip(),
            "equipment_type": str(row.get("type", "")).strip(),
            "quantity": int(row.get("qty", 1) or 1),
            "item_name": str(row.get("equipment", "")).strip(),
        }
        for row in raw
        if str(row.get("equipment", "")).strip()
    ]

    raw = get_worksheet(client, sid, event.schedule_tab).get_all_records()
    data["schedule"] = [
        {
            "title": str(row.get("name", "")).strip(),
            "room_name": str(row.get("room_name", "")).strip(),
            "room_number": str(row.get("room_number", "")).strip(),
            "building": str(row.get("building", "")).strip(),
            "av": str(row.get("av", "")).strip(),
            "description": str(row.get("desc", "")).strip(),
            "date": str(row.get("date", "")).strip(),
            "start_time": str(row.get("start_time", "")).strip(),
            "end_time": str(row.get("end_time", "")).strip(),
        }
        for row in raw
        if str(row.get("name", "")).strip()
    ]

    raw = get_worksheet(client, sid, event.staff_tab).get_all_records()
    data["staff"] = [
        {
            "staff_name": str(row.get("staff", "")).strip(),
            "date": str(row.get("date", "")).strip(),
            "start_time": str(row.get("start_time", "")).strip(),
            "end_time": str(row.get("end_time", "")).strip(),
            "notes": str(row.get("notes", "")).strip(),
        }
        for row in raw
        if str(row.get("staff", "")).strip()
    ]

    if event.checklist_tab:
        try:
            raw = get_worksheet(client, sid, event.checklist_tab).get_all_records()
            data["checklist"] = [
                {
                    "building": str(row.get("building", "")).strip(),
                    "room_name": str(row.get("room_name", "")).strip(),
                    "room_number": str(row.get("room_number", "")).strip(),
                    "item": str(row.get("item", "")).strip(),
                    "checked": str(row.get("checked", "")).strip().lower() in ("1", "true", "yes"),
                    "checked_by": str(row.get("checked_by", "")).strip(),
                    "checked_at": str(row.get("checked_at", "")).strip(),
                }
                for row in raw
                if str(row.get("item", "")).strip()
            ]
        except gspread.exceptions.WorksheetNotFound:
            data["checklist"] = None
    else:
        data["checklist"] = None

    return data
