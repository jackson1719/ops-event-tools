from .models import Event


def nav_events(request):
    """Event switcher + current event (resolved by URL slug) for the nav bar."""
    events = Event.objects.filter(is_active=True)
    current = None
    slug = request.resolver_match.kwargs.get("slug") if request.resolver_match else None
    if slug:
        current = next((e for e in events if e.slug == slug), None) or Event.objects.filter(slug=slug).first()
    return {"nav_events": events, "current_event": current}
