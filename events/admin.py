from django.contrib import admin

from .models import ChecklistItem, Equipment, Event, Link, Room, ScheduleItem, StaffShift


class EquipmentInline(admin.TabularInline):
    model = Equipment
    extra = 0


class ChecklistInline(admin.TabularInline):
    model = ChecklistItem
    extra = 0
    fields = ["position", "item", "checked", "checked_by", "checked_at"]


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active", "sheets_enabled", "last_sync_status", "last_sync_at"]
    prepopulated_fields = {"slug": ["name"]}
    readonly_fields = ["last_sync_at", "last_sync_status", "last_sync_error"]
    fieldsets = [
        (None, {"fields": ["name", "slug", "timezone", "is_active"]}),
        ("Google Sheets (optional)", {"fields": [
            "spreadsheet_id", "rooms_tab", "equipment_tab", "schedule_tab", "staff_tab", "checklist_tab",
        ]}),
        ("Sync status", {"fields": ["last_sync_at", "last_sync_status", "last_sync_error"]}),
    ]

    @admin.display(boolean=True)
    def sheets_enabled(self, obj):
        return obj.sheets_enabled


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ["building", "room_number", "name", "floor", "event"]
    list_filter = ["event", "building"]
    search_fields = ["name", "room_number"]
    inlines = [EquipmentInline, ChecklistInline]


@admin.register(ScheduleItem)
class ScheduleItemAdmin(admin.ModelAdmin):
    list_display = ["title", "building", "room_name", "room_number", "starts_at", "ends_at", "has_av", "event"]
    list_filter = ["event", "building", "has_av"]
    search_fields = ["title", "description"]
    date_hierarchy = "starts_at"


@admin.register(StaffShift)
class StaffShiftAdmin(admin.ModelAdmin):
    list_display = ["staff_name", "starts_at", "ends_at", "notes", "event"]
    list_filter = ["event"]
    search_fields = ["staff_name"]


@admin.register(Link)
class LinkAdmin(admin.ModelAdmin):
    list_display = ["title", "url", "category", "position", "event"]
    list_filter = ["event", "category"]
