from django.core.management.base import BaseCommand

from sync.backups import perform_backup


class Command(BaseCommand):
    help = "Take a backup (SQLite snapshot + media) into BACKUP_DIR immediately."

    def handle(self, *args, **options):
        path = perform_backup()
        self.stdout.write(self.style.SUCCESS(f"Backup written: {path}"))
