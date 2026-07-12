from django.core.management.base import BaseCommand, CommandError

from sync.acme_client import cert_expiry, issue_certificate


class Command(BaseCommand):
    help = "Issue/renew the HTTPS certificate now using the Site Settings ACME configuration."

    def handle(self, *args, **options):
        try:
            issue_certificate()
        except Exception as exc:
            raise CommandError(f"Issuance failed: {exc}")
        self.stdout.write(self.style.SUCCESS(f"Certificate issued; expires {cert_expiry()}"))
