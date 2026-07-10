from datetime import date

from django import template

from ..selectors import format_day as _format_day

register = template.Library()


@register.filter
def format_day(value):
    """'Friday (4/3)' for a date (or ISO date string)."""
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, date):
        return _format_day(value)
    return value


@register.filter
def role_at_least(user, minimum):
    from accounts.roles import has_role
    return has_role(user, minimum)
