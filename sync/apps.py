import sys

from django.apps import AppConfig


def _running_as_server() -> bool:
    """True under gunicorn or `runserver` — not for manage.py test/migrate/etc.
    (exact arg match, so `manage.py help runserver` doesn't start schedulers)."""
    import os

    if "gunicorn" in os.path.basename(sys.argv[0]):
        return True
    # runserver: only the reloader child (RUN_MAIN=true) should start threads,
    # or the parent when the reloader is disabled (--noreload).
    if len(sys.argv) > 1 and sys.argv[1] == "runserver":
        return os.environ.get("RUN_MAIN") == "true" or "--noreload" in sys.argv
    return False


class SyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sync"

    def ready(self):
        if _running_as_server():
            from .backups import start_backup_scheduler
            start_backup_scheduler()
            from .acme_client import start_renewal_scheduler
            start_renewal_scheduler()
