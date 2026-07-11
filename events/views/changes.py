from django.shortcuts import render

from accounts.roles import VIEWER, require_role
from ..shortcuts import get_event_or_404


@require_role(VIEWER)
def changes_page(request, slug):
    event = get_event_or_404(slug)

    # Group by sync run (rows in one run share an exact synced_at)
    runs = []
    current_key = None
    for change in event.schedule_changes.all()[:500]:
        if change.synced_at != current_key:
            current_key = change.synced_at
            runs.append({"synced_at": change.synced_at, "changes": []})
        runs[-1]["changes"].append(change)

    return render(request, "changes.html", {"event": event, "runs": runs})
