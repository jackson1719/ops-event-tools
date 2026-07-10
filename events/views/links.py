from django.shortcuts import render

from accounts.roles import VIEWER, require_role
from ..shortcuts import get_event_or_404


@require_role(VIEWER)
def links_page(request, slug):
    event = get_event_or_404(slug)
    categories = {}
    for link in event.links.all():
        categories.setdefault(link.category or "General", []).append(link)
    return render(request, "links.html", {"event": event, "categories": categories})
