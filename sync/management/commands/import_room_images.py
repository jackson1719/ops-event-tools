import os

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from events.models import Event

EXTENSIONS = ("jpg", "jpeg", "png", "gif", "webp")


def legacy_slug(room) -> str:
    """Old av-dashboard filename scheme: <building>_<room_number> lowercased."""
    return f"{room.building}_{room.room_number}".lower().replace(" ", "_").replace("/", "_").replace("-", "_")


class Command(BaseCommand):
    help = "Import room layout images from the legacy av-dashboard uploads directory."

    def add_arguments(self, parser):
        parser.add_argument("slug", help="Event slug")
        parser.add_argument("source_dir", help="Legacy room_images directory")
        parser.add_argument("--overwrite", action="store_true", help="Replace existing images")

    def handle(self, *args, **options):
        try:
            event = Event.objects.get(slug=options["slug"])
        except Event.DoesNotExist:
            raise CommandError(f"Unknown event: {options['slug']}")
        source_dir = options["source_dir"]
        if not os.path.isdir(source_dir):
            raise CommandError(f"Not a directory: {source_dir}")

        imported = 0
        unmatched = []
        rooms_by_slug = {legacy_slug(r): r for r in event.rooms.all()}

        for filename in sorted(os.listdir(source_dir)):
            base, _, ext = filename.rpartition(".")
            if ext.lower() not in EXTENSIONS:
                continue
            room = rooms_by_slug.get(base.lower())
            if room is None:
                unmatched.append(filename)
                continue
            if room.layout_image and not options["overwrite"]:
                self.stdout.write(f"skip (exists): {room}")
                continue
            with open(os.path.join(source_dir, filename), "rb") as f:
                if room.layout_image:
                    room.layout_image.delete(save=False)
                room.layout_image.save(filename, ContentFile(f.read()))
            imported += 1
            self.stdout.write(f"imported: {filename} -> {room}")

        self.stdout.write(self.style.SUCCESS(f"Imported {imported} image(s)."))
        if unmatched:
            self.stdout.write(self.style.WARNING(f"Unmatched files: {', '.join(unmatched)}"))
