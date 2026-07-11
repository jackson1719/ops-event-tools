import zoneinfo

from django import forms

from .models import Event


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
