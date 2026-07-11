from .themes import DEFAULT_THEME, THEMES


def theme(request):
    name = DEFAULT_THEME
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.theme in THEMES:
        name = user.theme
    return {
        "theme_name": name,
        "theme_base": THEMES[name]["base"],
        "themes": THEMES,
    }
