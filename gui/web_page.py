"""This app's face of shared/web_page.py (ADR 0016, ADR 0017).

The shared module cannot import an app's theme manager, so it takes the theme
as arguments. This binds Fulfilment's in, and every bridge keeps importing
from here.
"""

from pathlib import Path

from gui.theme_manager import get_theme_manager
from shared import web_page as _shared
from shared.web_page import (  # noqa: F401  (re-exported for the bridges and their tests)
    THEME_ACK_TIMEOUT_MS,
    THEME_MARKER,
    PageBridge,
    when_painted,
)

WEB_DIR = Path(__file__).resolve().parent / "web"


def mount_page(view, bridge, page, channel_name) -> None:
    """shared.web_page.mount_page with this app's tokens."""
    _shared.mount_page(
        view,
        bridge,
        page,
        channel_name,
        tokens=lambda: get_theme_manager().get_current_theme(),
    )


def switch_theme(name: str) -> None:
    """shared.web_page.switch_theme with this app's theme manager."""
    manager = get_theme_manager()
    _shared.switch_theme(
        name,
        current_name=manager.get_current_theme_name,
        tokens_for=manager.tokens_for,
        set_theme=manager.set_theme,
    )
