import secrets

from django.contrib.auth.models import AbstractUser
from django.db import models

from .themes import DEFAULT_THEME, THEME_CHOICES


class User(AbstractUser):
    staff_name = models.CharField(
        max_length=200, blank=True,
        help_text="Name exactly as it appears in the Staff Shifts sheet — links shifts to this account.",
    )
    ical_token = models.CharField(max_length=64, blank=True, editable=False)
    theme = models.CharField(max_length=20, choices=THEME_CHOICES, default=DEFAULT_THEME)

    def get_or_create_ical_token(self) -> str:
        if not self.ical_token:
            self.ical_token = secrets.token_urlsafe(32)
            self.save(update_fields=["ical_token"])
        return self.ical_token
