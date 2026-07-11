from django.contrib import admin, messages

from .audit import audit
from .models import AuditLog, ChecklistItem, Equipment, Event, Link, Room, ScheduleItem, StaffShift
from .services import clone_event


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
    actions = ["clone_selected"]

    @admin.action(description="Clone event (rooms, equipment, checklists, links — no schedule)")
    def clone_selected(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one event to clone.", messages.ERROR)
            return
        source = queryset.first()
        new_slug = f"{source.slug}-copy"
        if Event.objects.filter(slug=new_slug).exists():
            self.message_user(request, f"'{new_slug}' already exists — rename it first.", messages.ERROR)
            return
        new_event = clone_event(source, new_slug, f"{source.name} (copy)")
        audit(new_event, request.user, "clone", f"Cloned from {source.slug}")
        self.message_user(
            request,
            f"Cloned to '{new_event.slug}' ({new_event.rooms.count()} rooms). "
            "Rename it and set its spreadsheet ID.",
            messages.SUCCESS,
        )
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


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "action", "detail", "event"]
    list_filter = ["event", "action"]
    readonly_fields = ["event", "user", "action", "detail", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
