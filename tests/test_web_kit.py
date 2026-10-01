"""The web kit (phase 2 spec section 4), through a real Chromium. Never mark skip."""

import re
from pathlib import Path

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _rgb, _until_js

from gui.results_bridge import PAGE, THEME_MARKER, WEB_DIR
from shared.theme import DARK_THEME, LIGHT_THEME, theme_css_vars

SHEET = Path(__file__).resolve().parent / "web" / "kit_sheet.html"
KIT = WEB_DIR / "kit.css"
RESULTS_CSS = WEB_DIR / "results.css"

THEMES = pytest.mark.parametrize(
    "theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"]
)


def _sheet(qtbot, theme):
    view = QWebEngineView()
    qtbot.addWidget(view)
    html = SHEET.read_text(encoding="utf-8").replace(
        THEME_MARKER, theme_css_vars(theme)
    )
    view.setHtml(html, QUrl.fromLocalFile(str(WEB_DIR) + "/"))
    view.resize(1166, 720)
    view.show()
    # The stylesheet loads after the document: wait for a kit rule to apply.
    _until_js(
        qtbot,
        view,
        "!!document.querySelector('.card') && getComputedStyle("
        "document.querySelector('.card')).borderTopLeftRadius === '12px'",
    )
    return view


def _style(qtbot, view, selector, prop):
    return _eval(
        qtbot, view, f"getComputedStyle(document.querySelector({selector!r})).{prop}"
    )


def _selectors(css: str) -> list[str]:
    """Every selector list in a stylesheet, comments removed."""
    code = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    return [s.strip() for s in re.findall(r"([^{}]+)\{", code) if s.strip()]


def test_results_links_the_kit_before_its_own_stylesheet():
    html = PAGE.read_text(encoding="utf-8")
    assert 'href="kit.css"' in html
    assert html.index('href="kit.css"') < html.index('href="results.css"')


def test_the_kit_names_no_page():
    """Components only: an #id in the kit means a page leaked into it."""
    with_ids = [s for s in _selectors(KIT.read_text(encoding="utf-8")) if "#" in s]
    assert with_ids == []


def test_the_layer_scale_lives_in_the_kit_and_orders_the_layers():
    """A popover must never open underneath the selection bar, and the toast
    sits over everything. One scale for every page."""
    text = KIT.read_text(encoding="utf-8")
    z = {n: int(v) for n, v in re.findall(r"--z-([a-z]+):\s*(\d+)", text)}
    assert z["popover"] > z["bar"] > z["header"] > z["sticky"]
    assert z["toast"] > z["popover"]


@pytest.mark.parametrize("path", [KIT, RESULTS_CSS], ids=["kit", "results"])
def test_no_bare_z_index_survives(path):
    bare = re.findall(r"z-index:\s*(\d+)", path.read_text(encoding="utf-8"))
    assert bare == [], f"z-index must come from the layer scale, found {bare}"


@THEMES
def test_a_card_casts_a_shadow_in_light_and_draws_an_edge_in_dark(qtbot, theme):
    view = _sheet(qtbot, theme)
    shadow = _style(qtbot, view, ".card", "boxShadow")
    assert (shadow == "none") is (theme.name == "dark")
    assert _style(qtbot, view, ".card", "backgroundColor") == _rgb(theme.surface)


@THEMES
def test_each_button_role_takes_its_tokens(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#b-primary", "backgroundColor") == _rgb(theme.accent_fill)
    assert _style(qtbot, view, "#b-primary", "color") == _rgb(theme.on_accent)
    assert _style(qtbot, view, "#b-secondary", "borderTopColor") == _rgb(theme.border)
    assert _style(qtbot, view, "#b-dashed", "borderTopStyle") == "dashed"
    assert _style(qtbot, view, "#b-danger", "color") == _rgb(theme.status_danger)
    assert _style(qtbot, view, "#b-critical", "backgroundColor") == _rgb(theme.critical_fill)
    assert _style(qtbot, view, "#b-critical", "color") == _rgb(theme.on_critical)
    assert _style(qtbot, view, "#b-compact", "height") == "24px"


@THEMES
def test_a_disabled_button_drops_its_fill_and_dashes_its_edge(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#b-disabled", "borderTopStyle") == "dashed"
    assert _style(qtbot, view, "#b-disabled", "backgroundColor") == _rgb(
        theme.control_disabled_bg
    )
    assert _style(qtbot, view, "#b-disabled", "boxShadow") == "none"


@THEMES
def test_a_badge_is_a_tinted_pill_with_no_outline(qtbot, theme):
    view = _sheet(qtbot, theme)
    for role in ("success", "danger", "warning", "info"):
        selector = f"#g-{role}"
        assert _style(qtbot, view, selector, "backgroundColor") == _rgb(
            getattr(theme, f"status_{role}_bg")
        )
        assert _style(qtbot, view, selector, "color") == _rgb(
            getattr(theme, f"status_{role}")
        )
    assert _style(qtbot, view, "#g-success", "height") == "20px"
    assert _style(qtbot, view, "#g-neutral", "borderTopColor") == _rgb(theme.border_subtle)


@THEMES
def test_the_checked_segment_is_raised_and_the_rest_are_quiet(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#s-on", "backgroundColor") == _rgb(theme.surface)
    assert _style(qtbot, view, "#s-on", "fontWeight") == "700"
    assert _style(qtbot, view, "#s-off", "color") == _rgb(theme.text_secondary)
    assert _style(qtbot, view, ".segmented", "backgroundColor") == _rgb(theme.surface_sunken)


@THEMES
def test_the_banner_and_the_toast_take_their_planes(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#n-danger", "backgroundColor") == _rgb(theme.status_danger_bg)
    assert _style(qtbot, view, "#n-danger", "borderTopColor") == _rgb(
        theme.status_danger_border
    )
    assert _style(qtbot, view, "#n-neutral", "backgroundColor") == _rgb(theme.surface)
    assert _style(qtbot, view, "#t-toast", "backgroundColor") == _rgb(theme.surface_inverse)
    assert _style(qtbot, view, "#t-toast", "color") == _rgb(theme.on_inverse)


@THEMES
def test_a_checkbox_fills_with_the_accent_when_checked_or_mixed(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#c-off", "backgroundColor") == _rgb(theme.surface)
    assert _style(qtbot, view, "#c-off", "borderTopColor") == _rgb(theme.border)
    for box in ("#c-on", "#c-mixed"):
        assert _style(qtbot, view, box, "backgroundColor") == _rgb(theme.accent_fill)
    assert _style(qtbot, view, "#c-off", "width") == "16px"


@THEMES
def test_an_input_and_a_menu_take_their_edges(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#i-search", "borderTopColor") == _rgb(theme.border)
    assert _style(qtbot, view, "#i-invalid", "backgroundColor") == _rgb(theme.status_danger_bg)
    assert _style(qtbot, view, ".menu", "backgroundColor") == _rgb(theme.surface_overlay)
    assert _style(qtbot, view, ".menu", "borderTopColor") == _rgb(theme.border_subtle)
    assert _style(qtbot, view, "#m-danger", "color") == _rgb(theme.status_danger)
    assert _style(qtbot, view, ".page-title", "fontWeight") == "700"
