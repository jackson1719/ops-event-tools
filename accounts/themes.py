"""Theme registry. `base` is the Bootstrap color mode the theme builds on;
the theme name is also applied as a `theme-<name>` class on <html> for the
CSS variable overrides in static/css/app.css."""

THEMES = {
    "dark": {"label": "Dark", "base": "dark"},
    "light": {"label": "Light", "base": "light"},
    "midnight": {"label": "Midnight", "base": "dark"},
    "sakura": {"label": "Sakura", "base": "light"},
}

DEFAULT_THEME = "dark"

THEME_CHOICES = [(key, meta["label"]) for key, meta in THEMES.items()]
