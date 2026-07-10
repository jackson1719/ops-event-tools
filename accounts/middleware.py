from django.conf import settings


class HtmxLoginRedirectMiddleware:
    """When an HTMX partial request hits the login redirect, tell HTMX to do a
    full-page redirect instead of swapping the login page into a fragment."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            request.headers.get("HX-Request") == "true"
            and response.status_code == 302
            and response.get("Location", "").startswith(settings.LOGIN_URL)
        ):
            response.status_code = 401
            response["HX-Redirect"] = response["Location"]
        return response
