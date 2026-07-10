from django.core.management.base import BaseCommand, CommandError

from events.models import Event
from sync.engine import sync_event


class Command(BaseCommand):
    help = "Sync event data from Google Sheets. Pass event slugs, or --all for every active sheet-connected event."

    def add_arguments(self, parser):
        parser.add_argument("slugs", nargs="*", help="Event slugs to sync")
        parser.add_argument("--all", action="store_true", help="Sync all active events with a spreadsheet")

    def handle(self, *args, **options):
        if options["all"]:
            events = Event.objects.filter(is_active=True).exclude(spreadsheet_id="")
        elif options["slugs"]:
            events = Event.objects.filter(slug__in=options["slugs"])
            missing = set(options["slugs"]) - set(events.values_list("slug", flat=True))
            if missing:
                raise CommandError(f"Unknown event slug(s): {', '.join(sorted(missing))}")
        else:
            raise CommandError("Pass event slugs or --all")

        failures = 0
        for event in events:
            try:
                sync_event(event)
                self.stdout.write(self.style.SUCCESS(f"Synced {event.slug}"))
            except Exception as exc:
                failures += 1
                self.stderr.write(self.style.ERROR(f"Failed {event.slug}: {exc}"))
        if failures:
            raise CommandError(f"{failures} event(s) failed to sync")
