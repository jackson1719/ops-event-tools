from django.contrib.auth.decorators import login_not_required
from django.http import Http404, HttpResponse

from .models import AcmeChallenge


@login_not_required
def acme_challenge(request, token):
    """Serve HTTP-01 challenge responses; must be reachable anonymously."""
    try:
        challenge = AcmeChallenge.objects.get(token=token)
    except AcmeChallenge.DoesNotExist:
        raise Http404
    return HttpResponse(challenge.key_authorization, content_type="text/plain")
