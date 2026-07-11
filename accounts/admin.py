from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Event tools", {"fields": ["staff_name"]}),
    )
    list_display = ["username", "staff_name", "is_staff", "is_superuser"]
