from django.urls import path

from . import views, views_site, views_users

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("theme/", views.set_theme, name="set_theme"),
    path("users/", views_users.user_list, name="user_list"),
    path("users/new", views_users.user_create, name="user_create"),
    path("users/<int:user_id>/", views_users.user_edit, name="user_edit"),
    path("site-settings/", views_site.site_settings, name="site_settings"),
    path("site-settings/test-email", views_site.send_test_email, name="site_test_email"),
    path("site-settings/backup", views_site.trigger_backup, name="site_backup"),
    path("site-settings/issue-cert", views_site.issue_certificate, name="site_issue_cert"),
]
