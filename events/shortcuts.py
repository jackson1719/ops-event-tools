from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Event


def get_event_or_404(slug: str) -> Event:
    """Resolve the event and activate its timezone so template date filters
    (|date, |time) render in event-local time for the rest of the request."""
    event = get_object_or_404(Event, slug=slug)
    timezone.activate(event.tz)
    return event
