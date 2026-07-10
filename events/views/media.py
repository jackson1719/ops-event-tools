from django.conf import settings
from django.http import FileResponse, Http404
from django.utils._os import safe_join


def serve_media(request, path):
    """Login-required media serving (whitenoise only handles static assets).

    LoginRequiredMiddleware gates this view like everything else; room layout
    images should not be anonymous.
    """
    try:
        full_path = safe_join(settings.MEDIA_ROOT, path)
    except ValueError:
        raise Http404
    import os
    if not os.path.isfile(full_path):
        raise Http404
    return FileResponse(open(full_path, "rb"))
