import zoneinfo

from django.db import models


def _path_slug(value: str) -> str:
    """Filesystem-safe slug for a path component (no /, .., spaces)."""
    keep = [c if (c.isalnum() or c in "-_") else "_" for c in value]
    return "".join(keep) or "x"


def room_image_path(instance, filename):
    ext = _path_slug(filename.rsplit(".", 1)[-1].lower()) or "img"
    stem = f"{instance.pk or 'new'}_{_path_slug(instance.building)}_{_path_slug(instance.room_number)}"
    return f"room_images/{instance.event.slug}/{stem}.{ext}"


class Event(models.Model):
    """A convention/event — the tenant boundary for all data."""

    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    timezone = models.CharField(
        max_length=64,
        default="America/Los_Angeles",
        help_text="IANA timezone key, e.g. America/Los_Angeles",
    )
    is_active = models.BooleanField(default=True)

    # Optional Google Sheets connection. Blank spreadsheet_id = app-managed event.
    spreadsheet_id = models.CharField(max_length=100, blank=True)
    rooms_tab = models.CharField(max_length=100, blank=True, default="Rooms")
    equipment_tab = models.CharField(max_length=100, blank=True, default="Equipment")
    schedule_tab = models.CharField(max_length=100, blank=True, default="Events")
    staff_tab = models.CharField(max_length=100, blank=True, default="Staff Shifts")
    checklist_tab = models.CharField(
        max_length=100, blank=True, default="Room Checklist",
        help_text="Blank to disable checklist sync for this event.",
    )

    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=20, blank=True)  # success / error / running
    last_sync_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-is_active", "name"]

    def __str__(self):
        return self.name

    @property
    def tz(self):
        return zoneinfo.ZoneInfo(self.timezone)

    @property
    def sheets_enabled(self):
        return bool(self.spreadsheet_id)


class Room(models.Model):
    STATUS_CHOICES = [
        ("", "Not started"),
        ("in_progress", "In progress"),
        ("ready", "Ready"),
        ("issue", "Issue"),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="rooms")
    building = models.CharField(max_length=100)
    room_number = models.CharField(max_length=50, blank=True)
    name = models.CharField(max_length=200, blank=True)
    floor = models.CharField(max_length=50, blank=True)
    layout_image = models.ImageField(upload_to=room_image_path, blank=True)

    # Setup status — user data, preserved across syncs
    setup_status = models.CharField(max_length=20, blank=True, choices=STATUS_CHOICES, default="")
    status_note = models.CharField(max_length=300, blank=True)
    status_updated_by = models.CharField(max_length=100, blank=True)
    status_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["building", "floor", "room_number"]
        constraints = [
            models.UniqueConstraint(fields=["event", "building", "room_number"], name="uniq_room_per_event"),
        ]

    def __str__(self):
        return f"{self.building} {self.room_number} — {self.name}" if self.name else f"{self.building} {self.room_number}"

    @property
    def label(self):
        return f"{self.name} ({self.room_number})" if self.name and self.room_number else (self.name or self.room_number)


class Equipment(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="equipment")
    vendor = models.CharField(max_length=100, blank=True)
    equipment_type = models.CharField(max_length=50, blank=True)  # Audio / Video / Lighting
    quantity = models.PositiveIntegerField(default=1)
    item_name = models.CharField(max_length=200)

    class Meta:
        ordering = ["equipment_type", "item_name"]
        verbose_name_plural = "equipment"

    def __str__(self):
        return f"{self.quantity}x {self.item_name}"


class ScheduleItem(models.Model):
    """One row of the program grid (a panel, STRIKE, setup, etc.)."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="schedule_items")
    room = models.ForeignKey(Room, null=True, blank=True, on_delete=models.SET_NULL, related_name="schedule_items")
    # Denormalized sheet values — always populated; display fallback when room is None.
    building = models.CharField(max_length=100, blank=True)
    room_name = models.CharField(max_length=200, blank=True)
    room_number = models.CharField(max_length=50, blank=True)

    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    has_av = models.BooleanField(default=False)
    is_cancelled = models.BooleanField(default=False)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()

    class Meta:
        ordering = ["starts_at", "room_name", "room_number"]
        indexes = [models.Index(fields=["event", "starts_at"])]

    def __str__(self):
        return self.title

    @property
    def is_strike(self):
        return self.title.strip().upper() == "STRIKE"

    @property
    def room_label(self):
        if self.room_name and self.room_number:
            return f"{self.room_name} ({self.room_number})"
        return self.room_name or self.room_number


class StaffShift(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="staff_shifts")
    staff_name = models.CharField(max_length=200)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["starts_at", "staff_name"]
        indexes = [models.Index(fields=["event", "starts_at"])]

    def __str__(self):
        return f"{self.staff_name} ({self.starts_at:%m/%d %H:%M})"


class ChecklistItem(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="checklist_items")
    item = models.CharField(max_length=300)
    position = models.PositiveIntegerField(default=0)
    checked = models.BooleanField(default=False)
    checked_by = models.CharField(max_length=100, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.item


class ScheduleChange(models.Model):
    """A schedule difference detected between two syncs — how staff find out
    what programming changed overnight."""

    CHANGE_TYPES = [
        ("added", "Added"),
        ("removed", "Removed"),
        ("time_changed", "Time changed"),
        ("room_changed", "Room changed"),
        ("cancelled", "Cancelled"),
        ("uncancelled", "Un-cancelled"),
        ("av_changed", "AV changed"),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="schedule_changes")
    change_type = models.CharField(max_length=20, choices=CHANGE_TYPES)
    title = models.CharField(max_length=300)
    building = models.CharField(max_length=100, blank=True)
    room_label = models.CharField(max_length=260, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)  # new start if present, else old
    detail = models.CharField(max_length=500, blank=True)
    synced_at = models.DateTimeField()

    class Meta:
        ordering = ["-synced_at", "starts_at"]
        indexes = [models.Index(fields=["event", "-synced_at"])]

    def __str__(self):
        return f"{self.get_change_type_display()}: {self.title}"


class AuditLog(models.Model):
    """Who did what, when — checklist toggles, status changes, syncs, edits."""

    event = models.ForeignKey(Event, null=True, blank=True, on_delete=models.CASCADE, related_name="audit_logs")
    user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=40)  # checklist / room_status / sync / links / image / clone
    detail = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["event", "-created_at"])]

    def __str__(self):
        return f"{self.created_at:%m/%d %H:%M} {self.user} {self.action}"


class Link(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="links")
    title = models.CharField(max_length=200)
    url = models.URLField()
    description = models.CharField(max_length=500, blank=True)
    category = models.CharField(max_length=100, blank=True, default="General")
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["category", "position", "id"]

    def __str__(self):
        return self.title
