import zoneinfo

from django import forms
from django.forms import inlineformset_factory

from .models import ChecklistItem, Equipment, Event, Room, ScheduleItem, StaffShift


def bootstrapify(form):
    """Add Bootstrap classes to every field widget."""
    for field in form.fields.values():
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs.setdefault("class", "form-check-input")
        elif isinstance(field.widget, forms.Select):
            field.widget.attrs.setdefault("class", "form-select")
        else:
            field.widget.attrs.setdefault("class", "form-control")


class EventSettingsForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            "name", "timezone", "is_active",
            "spreadsheet_id", "rooms_tab", "equipment_tab",
            "schedule_tab", "staff_tab", "checklist_tab",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bootstrapify(self)

    def clean_timezone(self):
        value = self.cleaned_data["timezone"]
        try:
            zoneinfo.ZoneInfo(value)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            raise forms.ValidationError("Unknown timezone — use an IANA key like America/Los_Angeles.")
        return value


class EventCreateForm(EventSettingsForm):
    class Meta(EventSettingsForm.Meta):
        fields = ["name", "slug", "timezone", "spreadsheet_id"]


class _DateTimeLocalInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%dT%H:%M", **kwargs)


class _BootstrapModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bootstrapify(self)


class RoomForm(_BootstrapModelForm):
    class Meta:
        model = Room
        fields = ["building", "room_number", "name", "floor"]


class ScheduleItemForm(_BootstrapModelForm):
    class Meta:
        model = ScheduleItem
        fields = ["title", "building", "room_name", "room_number",
                  "starts_at", "ends_at", "has_av", "is_cancelled", "description"]
        widgets = {
            "starts_at": _DateTimeLocalInput(),
            "ends_at": _DateTimeLocalInput(),
            "description": forms.Textarea(attrs={"rows": 2}),
        }

    def clean(self):
        cleaned = super().clean()
        starts, ends = cleaned.get("starts_at"), cleaned.get("ends_at")
        if starts and ends and ends <= starts:
            raise forms.ValidationError("End must be after start.")
        return cleaned


class StaffShiftForm(_BootstrapModelForm):
    class Meta:
        model = StaffShift
        fields = ["staff_name", "starts_at", "ends_at", "notes"]
        widgets = {
            "starts_at": _DateTimeLocalInput(),
            "ends_at": _DateTimeLocalInput(),
        }

    def clean(self):
        cleaned = super().clean()
        starts, ends = cleaned.get("starts_at"), cleaned.get("ends_at")
        if starts and ends and ends <= starts:
            raise forms.ValidationError("End must be after start.")
        return cleaned


class _BootstrapFormSetForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bootstrapify(self)


EquipmentFormSet = inlineformset_factory(
    Room, Equipment, form=_BootstrapFormSetForm,
    fields=["equipment_type", "quantity", "item_name", "vendor"],
    extra=1, can_delete=True,
)

ChecklistFormSet = inlineformset_factory(
    Room, ChecklistItem, form=_BootstrapFormSetForm,
    fields=["position", "item"],
    extra=1, can_delete=True,
)
