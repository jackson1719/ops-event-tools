from django import forms
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password

from .models import User
from .roles import ROLE_ORDER


class UserForm(forms.Form):
    """Create/edit a user with a single role. is_staff is derived from role so
    Manager+ can reach the admin data pages."""

    username = forms.CharField(max_length=150)
    role = forms.ChoiceField(choices=[(r, r) for r in ROLE_ORDER], initial="Viewer")
    staff_name = forms.CharField(
        max_length=200, required=False,
        help_text="Name exactly as in the Staff Shifts sheet (links My Shifts).",
    )
    is_active = forms.BooleanField(required=False, initial=True)
    password = forms.CharField(
        widget=forms.PasswordInput, required=False,
        help_text="Leave blank to keep the current password.",
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        from events.forms import bootstrapify
        bootstrapify(self)
        if instance is not None:
            self.fields["username"].disabled = True
            self.fields["username"].initial = instance.username
            self.fields["role"].initial = next(
                (r for r in reversed(ROLE_ORDER) if instance.groups.filter(name=r).exists()),
                "Viewer",
            )
            self.fields["staff_name"].initial = instance.staff_name
            self.fields["is_active"].initial = instance.is_active
        else:
            self.fields["password"].required = True
            self.fields["password"].help_text = ""

    def clean_username(self):
        username = self.cleaned_data["username"]
        if self.instance is None and User.objects.filter(username=username).exists():
            raise forms.ValidationError("Username already exists.")
        return username

    def clean_password(self):
        password = self.cleaned_data["password"]
        if password:
            validate_password(password, self.instance)
        return password

    def save(self) -> User:
        data = self.cleaned_data
        user = self.instance or User(username=data["username"])
        user.staff_name = data["staff_name"]
        user.is_active = data["is_active"]
        user.is_staff = data["role"] in ("Manager", "Admin")  # admin data pages
        if data["password"]:
            user.set_password(data["password"])
        user.save()
        user.groups.set([Group.objects.get(name=data["role"])])
        return user
