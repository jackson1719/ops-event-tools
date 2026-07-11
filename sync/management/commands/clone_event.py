from django.core.management.base import BaseCommand, CommandError

from events.models import Event
from events.services import clone_event


class Command(BaseCommand):
    help = "Clone an event's rooms, equipment, checklists (unchecked), and links into a new event."

    def add_arguments(self, parser):
        parser.add_argument("source_slug")
        parser.add_argument("new_slug")
        parser.add_argument("--name", required=True, help="Name for the new event")

    def handle(self, *args, **options):
        try:
            source = Event.objects.get(slug=options["source_slug"])
        except Event.DoesNotExist:
            raise CommandError(f"Unknown event: {options['source_slug']}")
        if Event.objects.filter(slug=options["new_slug"]).exists():
            raise CommandError(f"Event already exists: {options['new_slug']}")

        new_event = clone_event(source, options["new_slug"], options["name"])
        self.stdout.write(self.style.SUCCESS(
            f"Cloned {source.slug} -> {new_event.slug}: "
            f"{new_event.rooms.count()} rooms, "
            f"{sum(r.equipment.count() for r in new_event.rooms.all())} equipment, "
            f"{new_event.links.count()} links. "
            "Set a spreadsheet ID on the new event to enable sync."
        ))
