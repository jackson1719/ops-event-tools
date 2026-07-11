from .models import AuditLog


def audit(event, user, action: str, detail: str = ""):
    AuditLog.objects.create(
        event=event,
        user=user if getattr(user, "is_authenticated", False) else None,
        action=action,
        detail=detail[:1000],
    )
