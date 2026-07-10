import json

from django.core.management.base import BaseCommand, CommandError

from events.models import Event, Link


class Command(BaseCommand):
    help = "Import links from the legacy av-dashboard data/links.json file."

    def add_arguments(self, parser):
        parser.add_argument("slug", help="Event slug")
        parser.add_argument("links_file", help="Path to legacy links.json")

    def handle(self, *args, **options):
        try:
            event = Event.objects.get(slug=options["slug"])
        except Event.DoesNotExist:
            raise CommandError(f"Unknown event: {options['slug']}")
        try:
            with open(options["links_file"]) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Cannot read {options['links_file']}: {exc}")

        created = 0
        for i, entry in enumerate(data):
            url = entry.get("url", "")
            if not entry.get("title") or not url.startswith(("http://", "https://")):
                continue
            Link.objects.get_or_create(
                event=event,
                title=entry["title"],
                url=url,
                defaults={
                    "description": entry.get("description", ""),
                    "category": entry.get("category") or "General",
                    "position": i,
                },
            )
            created += 1
        self.stdout.write(self.style.SUCCESS(f"Imported {created} link(s)."))
