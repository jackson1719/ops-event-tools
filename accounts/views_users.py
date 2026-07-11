"""User management pages (Admin role) — replaces the Django admin for users."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from events.audit import audit
from .forms import UserForm
from .models import User
from .roles import ADMIN, ROLE_ORDER, require_role


def _role_of(user):
    return next((r for r in reversed(ROLE_ORDER) if user.groups.filter(name=r).exists()), "—")


@require_role(ADMIN)
def user_list(request):
    users = User.objects.prefetch_related("groups").order_by("username")
    for u in users:
        u.role = _role_of(u)
    return render(request, "accounts/user_list.html", {"users": users})


@require_role(ADMIN)
def user_create(request):
    if request.method == "POST":
        form = UserForm(request.POST)
        if form.is_valid():
            user = form.save()
            audit(None, request.user, "users", f"Created user {user.username} ({form.cleaned_data['role']})")
            messages.success(request, f"User '{user.username}' created.")
            return redirect("accounts:user_list")
    else:
        form = UserForm()
    return render(request, "accounts/user_form.html", {"form": form, "target": None})


@require_role(ADMIN)
def user_edit(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if request.method == "POST":
        form = UserForm(request.POST, instance=target)
        if form.is_valid():
            if target == request.user and not form.cleaned_data["is_active"]:
                messages.error(request, "You can't deactivate your own account.")
            else:
                form.save()
                audit(None, request.user, "users", f"Updated user {target.username}")
                messages.success(request, f"User '{target.username}' saved.")
                return redirect("accounts:user_list")
    else:
        form = UserForm(instance=target)
    return render(request, "accounts/user_form.html", {"form": form, "target": target})
