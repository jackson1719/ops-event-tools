"""Create the four role groups. Group membership is the RBAC mechanism
(see accounts/roles.py); Manager/Admin additionally get model permissions
for the Django admin."""
from django.db import migrations

ROLES = ["Viewer", "Staff", "Manager", "Admin"]

MANAGER_MODELS = ["event", "room", "equipment", "scheduleitem", "staffshift", "checklistitem", "link"]


def create_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    groups = {}
    for name in ROLES:
        groups[name], _ = Group.objects.get_or_create(name=name)

    # Manager: change/add/delete event-data models in the admin (not Event add/delete)
    manager_perms = Permission.objects.filter(
        content_type__app_label="events",
        content_type__model__in=MANAGER_MODELS,
    ).exclude(codename__in=["add_event", "delete_event"])
    groups["Manager"].permissions.set(manager_perms)

    # Admin: everything in events + user management
    admin_perms = Permission.objects.filter(
        content_type__app_label__in=["events", "accounts", "auth"],
    )
    groups["Admin"].permissions.set(admin_perms)


def remove_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=ROLES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("events", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_groups, remove_groups),
    ]
