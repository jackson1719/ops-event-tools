"""Closed-signup adapters: accounts exist only when an Admin creates them.

Google and email-code logins authenticate EXISTING users (matched by email);
an unknown Google account lands on account/signup_closed.html and an unknown
email gets an inline form error (enumeration prevention is off — internal tool).
"""
from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        return False
