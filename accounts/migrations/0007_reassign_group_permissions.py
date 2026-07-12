"""Re-assign role-group model permissions, ensuring the Permission rows exist
first.

The original 0002_groups ran before the post_migrate signal had created the
events/accounts Permission rows (they don't exist yet mid-`migrate` on a fresh
database), so Manager/Admin groups were created with empty permission sets.
This migration forces permission creation for the relevant apps, then assigns
them idempotently — fixing fresh installs and self-healing existing ones.
"""
from django.contrib.auth.management import create_permissions
from django.db import migrations

ROLES = ["Viewer", "Staff", "Manager", "Admin"]
MANAGER_MODELS = ["event", "room", "equipment", "scheduleitem", "staffshift", "checklistitem", "link"]


def assign(apps, schema_editor):
    # Ensure Permission rows exist now (post_migrate hasn't run yet on fresh DBs)
    for app_label in ("events", "accounts", "auth"):
        app_config = apps.get_app_config(app_label)
        app_config.models_module = True  # create_permissions guards on this
        create_permissions(app_config, verbosity=0)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    manager, _ = Group.objects.get_or_create(name="Manager")
    manager.permissions.set(
        Permission.objects.filter(
            content_type__app_label="events",
            content_type__model__in=MANAGER_MODELS,
        ).exclude(codename__in=["add_event", "delete_event"])
    )

    admin, _ = Group.objects.get_or_create(name="Admin")
    admin.permissions.set(
        Permission.objects.filter(content_type__app_label__in=["events", "accounts", "auth"])
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_acmechallenge_siteconfig_acme_contact_email_and_more"),
        ("events", "0003_schedulechange"),
    ]

    operations = [migrations.RunPython(assign, noop)]
