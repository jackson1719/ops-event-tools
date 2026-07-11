"""Domain operations that don't belong in a view."""
from django.core.files.base import ContentFile
from django.db import transaction

from .models import ChecklistItem, Equipment, Event, Link, Room


@transaction.atomic
def clone_event(source: Event, new_slug: str, new_name: str) -> Event:
    """Copy an event's reusable setup — rooms (with layout images), equipment,
    checklist items (unchecked), and links — into a new event.

    Schedule items and staff shifts are NOT copied (new con, new program);
    the spreadsheet connection is left blank for the caller to configure.
    """
    new_event = Event.objects.create(
        name=new_name,
        slug=new_slug,
        timezone=source.timezone,
        is_active=True,
        rooms_tab=source.rooms_tab,
        equipment_tab=source.equipment_tab,
        schedule_tab=source.schedule_tab,
        staff_tab=source.staff_tab,
        checklist_tab=source.checklist_tab,
    )

    for room in source.rooms.all():
        old_image = room.layout_image
        new_room = Room.objects.create(
            event=new_event,
            building=room.building,
            room_number=room.room_number,
            name=room.name,
            floor=room.floor,
        )
        if old_image:
            old_image.open("rb")
            new_room.layout_image.save(
                old_image.name.rsplit("/", 1)[-1], ContentFile(old_image.read()),
            )
            old_image.close()

        Equipment.objects.bulk_create([
            Equipment(
                room=new_room,
                vendor=e.vendor,
                equipment_type=e.equipment_type,
                quantity=e.quantity,
                item_name=e.item_name,
            )
            for e in room.equipment.all()
        ])
        ChecklistItem.objects.bulk_create([
            ChecklistItem(room=new_room, item=c.item, position=c.position)
            for c in room.checklist_items.all()
        ])

    Link.objects.bulk_create([
        Link(
            event=new_event,
            title=link.title,
            url=link.url,
            description=link.description,
            category=link.category,
            position=link.position,
        )
        for link in source.links.all()
    ])

    return new_event
