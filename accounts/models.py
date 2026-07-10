from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom user model.

    No extra fields yet — declared up front because swapping the user model
    after the first migration is painful.
    """
