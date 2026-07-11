from datetime import timedelta

from django.utils import timezone

from .models import Event

RECENT_CHANGES_WINDOW_HOURS = 48


def nav_events(request):
    """Event switcher + current event (resolved by URL slug) for the nav bar."""
    events = Event.objects.filter(is_active=True)
    current = None
    slug = request.resolver_match.kwargs.get("slug") if request.resolver_match else None
    if slug:
        current = next((e for e in events if e.slug == slug), None) or Event.objects.filter(slug=slug).first()

    recent_changes = 0
    if current:
        recent_changes = current.schedule_changes.filter(
            synced_at__gte=timezone.now() - timedelta(hours=RECENT_CHANGES_WINDOW_HOURS)
        ).count()

    return {"nav_events": events, "current_event": current, "recent_changes": recent_changes}
