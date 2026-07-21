"""
Shared color palette for the ASCII portrait + info card, so the two panels sit
next to each other as one cohesive terminal. Pick a theme with the THEME env var
(default: catppuccin). Each theme maps semantic roles, not raw colors, so the
scripts never hardcode hex.

    THEME=tokyonight python scripts/make_info_card.py
"""
import os

THEMES = {
    # Catppuccin Mocha -- soft, warm, the crowd favorite
    "catppuccin": {
        "bg": "#1e1e2e", "bg2": "#181825", "frame": "#313244",
        "muted": "#9399b2", "ink": "#cdd6f4",
        "key": "#fab387", "section": "#89b4fa", "bullet": "#a6e3a1",
        "user": "#a6e3a1", "at": "#6c7086", "host": "#89dceb",
        "dots": ["#f38ba8", "#f9e2af", "#a6e3a1"],
    },
    # Tokyo Night -- cool, sleek, high-contrast
    "tokyonight": {
        "bg": "#1a1b26", "bg2": "#16161e", "frame": "#2f3549",
        "muted": "#565f89", "ink": "#c0caf5",
        "key": "#ff9e64", "section": "#7aa2f7", "bullet": "#9ece6a",
        "user": "#9ece6a", "at": "#565f89", "host": "#7dcfff",
        "dots": ["#f7768e", "#e0af68", "#9ece6a"],
    },
    # Rosé Pine -- muted, elegant, low-saturation
    "rosepine": {
        "bg": "#191724", "bg2": "#1f1d2e", "frame": "#26233a",
        "muted": "#6e6a86", "ink": "#e0def4",
        "key": "#f6c177", "section": "#c4a7e7", "bullet": "#9ccfd8",
        "user": "#9ccfd8", "at": "#6e6a86", "host": "#ebbcba",
        "dots": ["#eb6f92", "#f6c177", "#9ccfd8"],
    },
}


def get_theme():
    return THEMES.get(os.environ.get("THEME", "tokyonight"), THEMES["tokyonight"])
