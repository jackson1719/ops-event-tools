import sys

from django.apps import AppConfig


def _running_as_server() -> bool:
    """True under gunicorn or runserver — not for manage.py test/migrate/etc."""
    argv = " ".join(sys.argv)
    return "gunicorn" in sys.argv[0] or "runserver" in argv


class SyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sync"

    def ready(self):
        if _running_as_server():
            from .backups import start_backup_scheduler
            start_backup_scheduler()
            from .acme_client import start_renewal_scheduler
            start_renewal_scheduler()
