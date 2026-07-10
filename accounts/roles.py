"""Role hierarchy helpers.

Roles are Django Groups with a strict ordering. A user "has" a role if they
belong to that group or any higher one; superusers pass every check.
"""
from functools import wraps

from django.core.exceptions import PermissionDenied

VIEWER = "Viewer"
STAFF = "Staff"
MANAGER = "Manager"
ADMIN = "Admin"

ROLE_ORDER = [VIEWER, STAFF, MANAGER, ADMIN]


def has_role(user, minimum: str) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    min_idx = ROLE_ORDER.index(minimum)
    allowed = set(ROLE_ORDER[min_idx:])
    return user.groups.filter(name__in=allowed).exists()


def require_role(minimum: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not has_role(request.user, minimum):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator
