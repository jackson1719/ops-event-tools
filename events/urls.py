from django.urls import path

from .views import links, live, manage, picker, rooms, schedule, staff

app_name = "events"

urlpatterns = [
    path("", picker.event_picker, name="picker"),

    path("e/<slug:slug>/live", live.live_page, name="live"),

    path("e/<slug:slug>/schedule", schedule.schedule_page, name="schedule"),
    path("e/<slug:slug>/schedule/table", schedule.schedule_table, name="schedule_table"),
    path("e/<slug:slug>/schedule/rooms", schedule.schedule_rooms, name="schedule_rooms"),
    path("e/<slug:slug>/schedule/print", schedule.schedule_print, name="schedule_print"),

    path("e/<slug:slug>/rooms", rooms.rooms_page, name="rooms"),
    path("e/<slug:slug>/rooms/<int:room_id>", rooms.room_detail, name="room_detail"),
    path("e/<slug:slug>/rooms/<int:room_id>/status", rooms.set_room_status, name="room_status"),
    path("e/<slug:slug>/checklist/<int:item_id>/toggle", rooms.toggle_checklist, name="checklist_toggle"),
    path("e/<slug:slug>/status", rooms.status_board, name="status_board"),

    path("e/<slug:slug>/staff", staff.staff_page, name="staff"),
    path("e/<slug:slug>/staff/table", staff.staff_table, name="staff_table"),
    path("e/<slug:slug>/staff/on-shift", staff.staff_on_shift, name="staff_on_shift"),
    path("e/<slug:slug>/staff/timeline", staff.staff_timeline, name="staff_timeline"),
    path("e/<slug:slug>/staff/heatmap", staff.staff_heatmap, name="staff_heatmap"),
    path("e/<slug:slug>/staff/directory", staff.staff_directory, name="staff_directory"),
    path("e/<slug:slug>/staff/print", staff.staff_print, name="staff_print"),
    path("e/<slug:slug>/staff/mine", staff.staff_mine, name="staff_mine"),
    path("e/<slug:slug>/staff/my.ics", staff.my_shifts_ics, name="staff_ics"),

    path("e/<slug:slug>/links", links.links_page, name="links"),

    path("e/<slug:slug>/manage/", manage.dashboard, name="manage"),
    path("e/<slug:slug>/manage/sync", manage.trigger_sync, name="manage_sync"),
    path("e/<slug:slug>/manage/links", manage.edit_links, name="manage_links"),
    path("e/<slug:slug>/manage/room-images", manage.room_images, name="manage_room_images"),
    path("e/<slug:slug>/manage/room-images/<int:room_id>", manage.upload_room_image, name="manage_room_image_upload"),
    path("e/<slug:slug>/manage/room-images/bulk", manage.bulk_upload_room_images, name="manage_room_images_bulk"),
    path("e/<slug:slug>/manage/room-images/pdf", manage.upload_pdf, name="manage_room_images_pdf"),
    path("e/<slug:slug>/manage/room-images/pdf/<str:batch_id>/", manage.assign_pdf_pages, name="manage_pdf_assign"),
    path("e/<slug:slug>/manage/room-images/pdf/<str:batch_id>/save", manage.save_pdf_assignments, name="manage_pdf_save"),
]
