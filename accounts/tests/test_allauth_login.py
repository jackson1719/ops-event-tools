import re

from allauth.account.models import EmailAddress
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase

from accounts.forms import UserForm
from accounts.models import User


def make_user(username="kit", email="kit@example.com", role="Staff", password="pw"):
    user = User.objects.create_user(username, password=password, email=email)
    user.groups.add(Group.objects.get(name=role))
    if email:
        EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
    return user


class LoginByCodeTests(TestCase):
    def test_code_login_happy_path(self):
        make_user()
        resp = self.client.post("/accounts/login/code/", {"email": "kit@example.com"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        # Codes look like "TCBW-BGFG"
        code_match = re.search(r"^([A-Z0-9]{4}-[A-Z0-9]{4})$", mail.outbox[0].body, re.M)
        self.assertIsNotNone(code_match, f"no code found in email body: {mail.outbox[0].body!r}")
        resp = self.client.post("/accounts/login/code/confirm/", {"code": code_match.group(1)})
        self.assertEqual(resp.status_code, 302)
        resp = self.client.get("/e/whatever-404/live")
        self.assertEqual(resp.status_code, 404)  # authenticated (404, not login redirect)

    def test_unknown_email_gets_inline_error_and_no_mail(self):
        resp = self.client.post("/accounts/login/code/", {"email": "nobody@example.com"})
        self.assertEqual(resp.status_code, 200)  # re-renders form with error
        self.assertEqual(len(mail.outbox), 0)

    def test_code_pages_reachable_anonymously(self):
        self.assertEqual(self.client.get("/accounts/login/code/").status_code, 200)

    def test_user_management_still_protected(self):
        resp = self.client.get("/accounts/users/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])
        staffer = make_user("s2", "s2@example.com", "Staff")
        self.client.force_login(staffer)
        self.assertEqual(self.client.get("/accounts/users/").status_code, 403)


class ClosedSignupTests(TestCase):
    def test_account_adapter_closed(self):
        from accounts.adapters import AccountAdapter
        self.assertFalse(AccountAdapter().is_open_for_signup(None))

    def test_social_adapter_closed(self):
        from accounts.adapters import SocialAccountAdapter
        self.assertFalse(SocialAccountAdapter().is_open_for_signup(None, None))

    def test_social_email_auth_keeps_password_usable(self):
        """The wipe_password guard: email-auth into a user with a VERIFIED
        EmailAddress must not destroy their local password."""
        from allauth.socialaccount.internal.flows.email_authentication import wipe_password
        from django.test import RequestFactory

        user = make_user()
        wipe_password(RequestFactory().get("/"), user, "kit@example.com")
        user.refresh_from_db()
        self.assertTrue(user.has_usable_password())

    def test_wipe_password_fires_without_verified_email(self):
        """Documents WHY the UserForm sync marks emails verified."""
        from allauth.socialaccount.internal.flows.email_authentication import wipe_password
        from django.test import RequestFactory

        user = User.objects.create_user("noverify", password="pw", email="nv@example.com")
        # No EmailAddress row at all
        wipe_password(RequestFactory().get("/"), user, "nv@example.com")
        user.refresh_from_db()
        self.assertFalse(user.has_usable_password())


class UserFormEmailSyncTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("boss", password="pw")
        self.admin.groups.add(Group.objects.get(name="Admin"))

    def form_save(self, instance=None, **overrides):
        data = {
            "username": overrides.get("username", "newbie"),
            "email": overrides.get("email", ""),
            "role": overrides.get("role", "Viewer"),
            "staff_name": "",
            "is_active": "on",
            "password": overrides.get("password", "a-good-password-42" if instance is None else ""),
        }
        form = UserForm(data, instance=instance)
        self.assertTrue(form.is_valid(), form.errors)
        return form.save()

    def test_email_creates_verified_address(self):
        user = self.form_save(email="new@example.com")
        addr = EmailAddress.objects.get(user=user)
        self.assertEqual(addr.email, "new@example.com")
        self.assertTrue(addr.verified)
        self.assertTrue(addr.primary)

    def test_email_change_replaces_address(self):
        user = self.form_save(email="old@example.com")
        self.form_save(instance=user, username=user.username, email="new@example.com")
        addresses = EmailAddress.objects.filter(user=user)
        self.assertEqual(addresses.count(), 1)
        self.assertEqual(addresses.get().email, "new@example.com")

    def test_email_cleared_removes_address(self):
        user = self.form_save(email="gone@example.com")
        self.form_save(instance=user, username=user.username, email="")
        self.assertFalse(EmailAddress.objects.filter(user=user).exists())

    def test_duplicate_email_rejected(self):
        self.form_save(email="taken@example.com")
        form = UserForm({
            "username": "second", "email": "TAKEN@example.com", "role": "Viewer",
            "staff_name": "", "is_active": "on", "password": "a-good-password-42",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)
