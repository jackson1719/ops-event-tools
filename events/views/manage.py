import glob
import os
import shutil
import threading
import uuid

from django.conf import settings
from django.contrib import messages
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.roles import MANAGER, require_role
from ..models import Link, Room
from ..shortcuts import get_event_or_404

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}


def _allowed_image(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def _room_slug(room: Room) -> str:
    """Legacy bulk-upload filename slug: <building>_<room_number> lowercased."""
    return f"{room.building}_{room.room_number}".lower().replace(" ", "_").replace("/", "_").replace("-", "_")


@require_role(MANAGER)
def dashboard(request, slug):
    event = get_event_or_404(slug)
    return render(request, "manage/dashboard.html", {"event": event})


@require_role(MANAGER)
@require_POST
def trigger_sync(request, slug):
    event = get_event_or_404(slug)
    if not event.sheets_enabled:
        messages.warning(request, "This event has no spreadsheet configured.")
        return redirect("events:manage", slug=slug)

    from sync.engine import sync_event_in_thread
    threading.Thread(target=sync_event_in_thread, args=(event.pk,), daemon=True).start()
    messages.info(request, "Sync started in background.")
    return redirect("events:manage", slug=slug)


@require_role(MANAGER)
def edit_links(request, slug):
    event = get_event_or_404(slug)
    if request.method == "POST":
        titles = request.POST.getlist("title")
        urls = request.POST.getlist("url")
        descriptions = request.POST.getlist("description")
        categories = request.POST.getlist("category")
        new_links = []
        for i, title in enumerate(titles):
            url = urls[i].strip() if i < len(urls) else ""
            if title.strip() and url.startswith(("http://", "https://")):
                new_links.append(Link(
                    event=event,
                    title=title.strip(),
                    url=url,
                    description=descriptions[i].strip() if i < len(descriptions) else "",
                    category=(categories[i].strip() if i < len(categories) else "") or "General",
                    position=i,
                ))
        event.links.all().delete()
        Link.objects.bulk_create(new_links)
        messages.success(request, "Links saved.")
        return redirect("events:manage_links", slug=slug)

    return render(request, "manage/links_edit.html", {"event": event, "links": event.links.all()})


@require_role(MANAGER)
def room_images(request, slug):
    event = get_event_or_404(slug)
    rooms = list(event.rooms.all())
    for room in rooms:
        room.upload_slug = _room_slug(room)
    return render(request, "manage/room_images.html", {"event": event, "rooms": rooms})


@require_role(MANAGER)
@require_POST
def upload_room_image(request, slug, room_id):
    event = get_event_or_404(slug)
    room = get_object_or_404(Room, pk=room_id, event=event)

    file = request.FILES.get("image")
    if not file or not file.name:
        messages.warning(request, "No file selected.")
        return redirect("events:manage_room_images", slug=slug)
    if not _allowed_image(file.name):
        messages.error(request, "Invalid file type. Use jpg, png, gif, or webp.")
        return redirect("events:manage_room_images", slug=slug)

    if room.layout_image:
        room.layout_image.delete(save=False)
    room.layout_image = file
    room.save()
    messages.success(request, f"Image uploaded for {room}.")
    return redirect("events:manage_room_images", slug=slug)


@require_role(MANAGER)
@require_POST
def bulk_upload_room_images(request, slug):
    """Multiple files named <building>_<room_number>.<ext> auto-match rooms."""
    event = get_event_or_404(slug)
    files = request.FILES.getlist("images")
    if not files:
        messages.warning(request, "No files selected.")
        return redirect("events:manage_room_images", slug=slug)

    rooms_by_slug = {_room_slug(r): r for r in event.rooms.all()}

    uploaded = 0
    skipped = []
    for file in files:
        if not file.name or not _allowed_image(file.name):
            skipped.append(file.name or "unknown")
            continue
        name_part = file.name.rsplit(".", 1)[0].lower()
        room = rooms_by_slug.get(name_part)
        if room is None:
            skipped.append(file.name)
            continue
        if room.layout_image:
            room.layout_image.delete(save=False)
        room.layout_image = file
        room.save()
        uploaded += 1

    msg = f"Uploaded {uploaded} image{'s' if uploaded != 1 else ''}."
    if skipped:
        msg += f" Skipped {len(skipped)}: {', '.join(skipped[:5])}"
        if len(skipped) > 5:
            msg += f" and {len(skipped) - 5} more"
    messages.add_message(request, messages.SUCCESS if uploaded else messages.WARNING, msg)
    return redirect("events:manage_room_images", slug=slug)


def _pdf_batch_dir(batch_id: str) -> str:
    return os.path.join(settings.MEDIA_ROOT, "pdf_temp", batch_id)


@require_role(MANAGER)
@require_POST
def upload_pdf(request, slug):
    """Upload a PDF, convert pages to images, then show assignment page."""
    event = get_event_or_404(slug)
    file = request.FILES.get("pdf")
    if not file or not file.name.lower().endswith(".pdf"):
        messages.error(request, "Please upload a PDF file.")
        return redirect("events:manage_room_images", slug=slug)

    try:
        from pdf2image import convert_from_bytes
    except ImportError:
        messages.error(request, "pdf2image not installed on the server.")
        return redirect("events:manage_room_images", slug=slug)

    batch_id = uuid.uuid4().hex[:12]
    batch_dir = _pdf_batch_dir(batch_id)
    os.makedirs(batch_dir, exist_ok=True)

    try:
        images = convert_from_bytes(file.read(), dpi=200, fmt="png")
    except Exception as exc:
        messages.error(request, f"Failed to convert PDF: {exc}")
        return redirect("events:manage_room_images", slug=slug)

    for i, img in enumerate(images):
        img.save(os.path.join(batch_dir, f"page_{i + 1:03d}.png"), "PNG")

    messages.info(request, f"PDF converted: {len(images)} pages. Assign each page to a room below.")
    return redirect("events:manage_pdf_assign", slug=slug, batch_id=batch_id)


@require_role(MANAGER)
def assign_pdf_pages(request, slug, batch_id):
    event = get_event_or_404(slug)
    batch_id = "".join(c for c in batch_id if c.isalnum())
    batch_dir = _pdf_batch_dir(batch_id)
    if not os.path.isdir(batch_dir):
        messages.error(request, "PDF batch not found.")
        return redirect("events:manage_room_images", slug=slug)

    pages = sorted(os.path.basename(p) for p in glob.glob(os.path.join(batch_dir, "page_*.png")))
    return render(request, "manage/pdf_assign.html", {
        "event": event,
        "batch_id": batch_id,
        "pages": pages,
        "rooms": event.rooms.all(),
    })


@require_role(MANAGER)
@require_POST
def save_pdf_assignments(request, slug, batch_id):
    event = get_event_or_404(slug)
    batch_id = "".join(c for c in batch_id if c.isalnum())
    batch_dir = _pdf_batch_dir(batch_id)
    if not os.path.isdir(batch_dir):
        messages.error(request, "PDF batch not found.")
        return redirect("events:manage_room_images", slug=slug)

    rooms_by_id = {str(r.pk): r for r in event.rooms.all()}

    assigned = 0
    for key, value in request.POST.items():
        if not key.startswith("page_") or not value:
            continue
        page_path = os.path.join(batch_dir, os.path.basename(key) + ".png")
        room = rooms_by_id.get(value)
        if room is None or not os.path.exists(page_path):
            continue
        with open(page_path, "rb") as f:
            if room.layout_image:
                room.layout_image.delete(save=False)
            room.layout_image.save(f"{_room_slug(room)}.png", ContentFile(f.read()))
        assigned += 1

    shutil.rmtree(batch_dir, ignore_errors=True)
    messages.success(request, f"Assigned {assigned} page{'s' if assigned != 1 else ''} to rooms.")
    return redirect("events:manage_room_images", slug=slug)
