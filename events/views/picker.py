from django.shortcuts import redirect, render

from ..models import Event


def event_picker(request):
    events = Event.objects.filter(is_active=True)
    if events.count() == 1:
        return redirect("events:live", slug=events.first().slug)
    return render(request, "picker.html", {"events": events})
