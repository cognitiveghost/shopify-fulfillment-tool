"""Tests for the build-gate probe page.

Only build_gate_html is tested. run_gate spawns a Chromium helper process
and is verified by a human running the frozen build on Windows -- that is
the entire point of the gate.
"""
import re

from gui.theme_manager import get_theme_manager
from gui.webengine_gate import build_gate_html


def _theme():
    return get_theme_manager().get_current_theme()


def test_page_uses_theme_colours_not_literals():
    theme = _theme()
    html = build_gate_html(theme, startup_seconds=1.5, load_seconds=0.25, accommodations=[])

    assert theme.surface in html
    assert theme.text in html
    assert theme.accent_fill in html

    # Every hex in the page must be one the theme handed us. A stray literal
    # here would make the page prove less than it claims: it would render
    # correctly even if theme values never reached the view.
    theme_hexes = {v.lower() for v in vars(theme).values() if isinstance(v, str) and v.startswith("#")}
    for found in re.findall(r"#[0-9a-fA-F]{3,8}", html):
        assert found.lower() in theme_hexes, f"hardcoded colour {found} in the gate page"


def test_page_reports_its_measurements():
    html = build_gate_html(_theme(), startup_seconds=2.5, load_seconds=0.75, accommodations=[])
    assert "2.50" in html
    assert "0.75" in html


def test_page_reports_a_pending_load_before_it_finishes():
    html = build_gate_html(_theme(), startup_seconds=2.5, load_seconds=None, accommodations=[])
    assert "2.50" in html
    assert "measuring" in html.lower()


def test_page_names_the_accommodations_in_effect():
    html = build_gate_html(
        _theme(), startup_seconds=1.0, load_seconds=0.1, accommodations=["--disable-gpu"]
    )
    assert "--disable-gpu" in html


def test_page_says_so_when_no_accommodation_was_needed():
    html = build_gate_html(_theme(), startup_seconds=1.0, load_seconds=0.1, accommodations=[])
    assert "none" in html.lower()
