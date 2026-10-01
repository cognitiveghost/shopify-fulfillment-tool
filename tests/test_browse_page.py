"""The Browse page, driven through a real Chromium (phase 4 spec section 5).

Every test pushes a state built by browse_state() and reads the DOM back.
1166x720 is the page a 1366x768 window gives. Never mark skip.
"""

import json

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_browse_state import D, H, make_state, session
from test_results_bridge import _eval, _rgb, _until_js

from gui.browse_bridge import PAGE, mount_browse_page
from gui.theme_manager import get_theme_manager
from gui.web_page import THEME_MARKER

# Newest first, as SessionManager.list_client_sessions returns them.
SESSIONS = [
    session("2026-09-30_2", age=3 * H, orders=64, items=131),
    session(
        "2026-09-30_1", age=6 * H, orders=1197, items=2402, blocked=9, lists=4, done=3,
        comment="Morning wave, DHL pickup 15:00",
    ),
    session("2026-09-29_2", age=1 * D, orders=142, items=296, lists=3, done=2, comment="Evening wave"),
    session("2026-09-29_1", age=1 * D, status="completed", lists=3, done=3),
    session("2026-09-28_1", age=2 * D, blocked=3, lists=2, paused=True, comment="Waiting on SRM-30ML restock"),
    session("2026-09-26_2", age=4 * D, status="completed", lists=5, done=4, comment="8 orders back on shelf"),
    session("2026-09-24_1", age=6 * D, status="abandoned", comment="Duplicate import of 09-23"),
    session("2026-09-23_1", age=9 * D, lists=3, done=1, idle=8 * D),
    session("2026-09-05_1", age=26 * D, status="completed", lists=2, done=2),
    session("2026-08-20_1", age=41 * D, status="archived", lists=2, done=2),
    session("2026-08-18_1", age=43 * D, status="archived", lists=2, done=2),
]
ALL = [s["session_name"] for s in SESSIONS[:9]]
ATTENTION = ["2026-09-30_1", "2026-09-28_1", "2026-09-26_2", "2026-09-23_1"]


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_browse_page(view)
    view.resize(1166, 720)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def _renders(qtbot, view):
    return _eval(qtbot, view, "Number(document.documentElement.dataset.renders || 0)")


def _show(qtbot, view, bridge, state):
    """Push a state and wait for the page to have drawn it."""
    before = _renders(qtbot, view)
    bridge.set_state(state)
    _until_js(qtbot, view, f"Number(document.documentElement.dataset.renders) > {before}")


@pytest.fixture
def listed(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(SESSIONS))
    return view, bridge


def _json(qtbot, view, expr):
    """A list or an object from the page: runJavaScript hands back only scalars."""
    return json.loads(_eval(qtbot, view, f"JSON.stringify({expr})"))


def _text(qtbot, view, selector):
    return _eval(
        qtbot,
        view,
        f"document.querySelector({selector!r}).textContent.replace(/\\s+/g, ' ').trim()",
    )


def _texts(qtbot, view, selector):
    return _json(
        qtbot,
        view,
        f"Array.from(document.querySelectorAll({selector!r}))"
        ".map(e => e.textContent.replace(/\\s+/g, ' ').trim())",
    )


def _count(qtbot, view, selector):
    return _eval(qtbot, view, f"document.querySelectorAll({selector!r}).length")


def _click(qtbot, view, selector):
    _eval(qtbot, view, f"document.querySelector({selector!r}).click(); true")


def _hidden(qtbot, view, element_id):
    return _eval(qtbot, view, f"document.getElementById({element_id!r}).hidden")


def _style(qtbot, view, selector, prop):
    return _eval(qtbot, view, f"getComputedStyle(document.querySelector({selector!r})).{prop}")


def _rows(qtbot, view):
    """The session names drawn, top to bottom."""
    return _json(qtbot, view, "Array.from(document.querySelectorAll('.row')).map(r => r.dataset.row)")


def _row(name):
    return f'[data-row="{name}"]'


def _check(qtbot, view, *names):
    for name in names:
        _click(qtbot, view, _row(name))


def _search(qtbot, view, text):
    _eval(
        qtbot,
        view,
        f"(function () {{ var s = document.getElementById('search'); s.value = {text!r};"
        " s.dispatchEvent(new Event('input')); return true; })()",
    )


def _key(qtbot, view, selector, key, ctrl=False):
    _eval(
        qtbot,
        view,
        f"document.querySelector({selector!r}).dispatchEvent(new KeyboardEvent('keydown',"
        f" {{key: {key!r}, ctrlKey: {str(ctrl).lower()}, bubbles: true, cancelable: true}})); true",
    )


def _focused(qtbot, view):
    return _eval(qtbot, view, "(document.activeElement.dataset.key || document.activeElement.id)")


def _never(qtbot, signal):
    """Give a signal that must not fire the time to fire."""
    with qtbot.assertNotEmitted(signal, wait=300):
        pass


def test_the_page_carries_the_theme_marker_exactly_once():
    assert PAGE.read_text(encoding="utf-8").count(THEME_MARKER) == 1


def test_the_page_links_the_kit_before_its_own_stylesheet():
    html = PAGE.read_text(encoding="utf-8")
    assert html.index('href="kit.css"') < html.index('href="browse.css"')


# --- views -------------------------------------------------------------------


def test_no_client_shows_one_panel_and_no_list(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(client=""))
    assert _eval(qtbot, view, "document.getElementById('browse').dataset.view") == "no_client"
    assert _text(qtbot, view, "#panel .state-title") == "Choose a client"
    assert _text(qtbot, view, "#panel .state-text") == (
        "Pick a client in the bar above to see its sessions."
    )
    assert _count(qtbot, view, "#panel .btn") == 0
    assert _hidden(qtbot, view, "card") is True


def test_a_client_with_no_sessions_offers_a_new_one(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state([]))
    assert _text(qtbot, view, "#panel .state-title") == "No sessions yet"
    assert _text(qtbot, view, "#panel .state-text") == (
        "CLIENT_ACME has no sessions on the file server."
    )
    assert "primary" in _eval(
        qtbot, view, "document.querySelector(\"[data-act='new-session']\").className"
    )
    with qtbot.waitSignal(bridge.newSessionRequested, timeout=5000):
        _click(qtbot, view, "[data-act='new-session']")


def test_a_failed_load_says_so_and_offers_to_try_again(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(failed=True))
    assert _text(qtbot, view, "#panel .state-title") == "Sessions didn't load"
    assert _text(qtbot, view, "#panel .state-text") == "Details are in Logs."
    with qtbot.waitSignal(bridge.refreshRequested, timeout=5000):
        _click(qtbot, view, "[data-act='refresh']")


def test_loading_shows_the_skeleton_and_quiet_controls(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(SESSIONS, loading=True))
    assert _hidden(qtbot, view, "card") is False
    assert _count(qtbot, view, ".sk-row") == 10
    assert _count(qtbot, view, ".row") == 0
    assert _text(qtbot, view, ".loading-line") == "Reading sessions from the server…"
    assert _texts(qtbot, view, ".tab .segment-count") == ["–"] * 5
    assert _text(qtbot, view, "#count") == "Reading…"
    assert _eval(qtbot, view, "document.getElementById('refresh').disabled") is True
    assert _eval(qtbot, view, "document.getElementById('head-check').disabled") is True
    assert _count(qtbot, view, "#footer [data-act]") == 0


def test_refresh_asks_python(qtbot, listed):
    view, bridge = listed
    assert _eval(qtbot, view, "document.getElementById('refresh').title") == "Refresh  F5"
    with qtbot.waitSignal(bridge.refreshRequested, timeout=5000):
        _click(qtbot, view, "#refresh")


# --- tabs and search ---------------------------------------------------------


def test_the_tabs_count_their_sessions(qtbot, listed):
    view, _bridge = listed
    assert _texts(qtbot, view, ".tab") == [
        "All9", "Active5", "Completed3", "Abandoned1", "Archived2",
    ]
    assert _eval(qtbot, view, "document.querySelector('[data-tab=\"all\"]').getAttribute('aria-selected')") == "true"
    assert _text(qtbot, view, "#count") == "9 sessions"
    assert _rows(qtbot, view) == ATTENTION + [n for n in ALL if n not in ATTENTION]


def test_a_tab_filters_by_the_stored_status_and_unchecks(qtbot, listed):
    view, _bridge = listed
    _check(qtbot, view, "2026-09-29_1")
    assert _hidden(qtbot, view, "selbar") is False

    _click(qtbot, view, '[data-tab="completed"]')

    assert _rows(qtbot, view) == ["2026-09-26_2", "2026-09-29_1", "2026-09-05_1"]
    assert _text(qtbot, view, "#count") == "3 sessions"
    assert _hidden(qtbot, view, "selbar") is True
    assert _count(qtbot, view, ".row.checked") == 0
    _click(qtbot, view, '[data-tab="archived"]')
    assert _rows(qtbot, view) == ["2026-08-20_1", "2026-08-18_1"]


def test_arrow_keys_walk_the_tabs(qtbot, listed):
    view, _bridge = listed
    _eval(qtbot, view, "document.querySelector('[data-tab=\"all\"]').focus(); true")
    _key(qtbot, view, "#tabs .tab[aria-selected='true']", "ArrowRight")
    assert _focused(qtbot, view) == "tab-active"
    assert _text(qtbot, view, "#count") == "5 sessions"
    _key(qtbot, view, "#tabs .tab[aria-selected='true']", "ArrowLeft")
    _key(qtbot, view, "#tabs .tab[aria-selected='true']", "ArrowLeft")
    assert _focused(qtbot, view) == "tab-archived"


def test_search_matches_a_name_or_a_comment(qtbot, listed):
    view, _bridge = listed
    _search(qtbot, view, "DHL ")
    assert _rows(qtbot, view) == ["2026-09-30_1"]
    assert _text(qtbot, view, "#count") == "1 of 9 sessions"
    _search(qtbot, view, "09-29")
    assert _rows(qtbot, view) == ["2026-09-29_2", "2026-09-29_1"]
    assert _texts(qtbot, view, ".tab .segment-count") == ["9", "5", "3", "1", "2"]


def test_typing_in_search_unchecks(qtbot, listed):
    view, _bridge = listed
    _check(qtbot, view, "2026-09-29_1")
    _search(qtbot, view, "09")
    assert _hidden(qtbot, view, "selbar") is True


def test_one_session_is_counted_in_the_singular(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(SESSIONS[:1]))
    assert _text(qtbot, view, "#count") == "1 session"


def test_a_search_with_no_match_offers_to_clear_it(qtbot, listed):
    view, _bridge = listed
    _search(qtbot, view, "2025-12")
    assert _count(qtbot, view, ".row") == 0
    assert _text(qtbot, view, "#list .state-title") == "No sessions match"
    assert _text(qtbot, view, "#list .state-text") == (
        "Nothing in All has “2025-12” in its name or comment."
    )
    assert _text(qtbot, view, "#count") == "0 of 9 sessions"

    _click(qtbot, view, "[data-act='clear-search']")

    assert _eval(qtbot, view, "document.getElementById('search').value") == ""
    assert len(_rows(qtbot, view)) == 9


def test_the_search_text_is_quoted_as_text(qtbot, listed):
    view, _bridge = listed
    _search(qtbot, view, '<b>"X"</b>')
    assert _text(qtbot, view, "#list .state-text") == (
        'Nothing in All has “<b>"X"</b>” in its name or comment.'
    )
    assert _count(qtbot, view, "#list b") == 0


def test_an_empty_tab_says_so_and_offers_nothing(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state([s for s in SESSIONS if s["status"] != "abandoned"]))
    _click(qtbot, view, '[data-tab="abandoned"]')
    assert _text(qtbot, view, "#list .state-title") == "Nothing in Abandoned"
    assert _text(qtbot, view, "#list .state-text") == "No session of this client is abandoned."
    assert _count(qtbot, view, "#list .btn") == 0


def test_a_client_whose_sessions_are_all_archived_offers_to_show_them(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(SESSIONS[9:]))
    assert _text(qtbot, view, "#list .state-title") == "Nothing in All"
    assert _text(qtbot, view, "#list .state-text") == "Every session of this client is archived."

    _click(qtbot, view, "#list [data-act='toggle-archived']")

    assert _rows(qtbot, view) == ["2026-08-20_1", "2026-08-18_1"]


# --- groups and rows ---------------------------------------------------------


def test_needs_attention_comes_first_and_says_why(qtbot, listed):
    view, _bridge = listed
    assert _texts(qtbot, view, ".group-label") == ["Needs attention", "Everything else"]
    assert _texts(qtbot, view, ".group-count") == ["4", "5"]
    assert _texts(qtbot, view, ".group-note") == [
        "1 paused · 1 stale · 1 incomplete · 1 with blocked orders",
        "",
    ]
    assert _count(qtbot, view, "[data-group='attention'] .group-dot") == 1
    assert _count(qtbot, view, "[data-group='rest'] .group-dot") == 0
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, ".group-dot", "backgroundColor") == _rgb(theme.status_warning)


def test_with_nothing_needing_attention_the_one_group_takes_the_tabs_name(qtbot, listed):
    view, _bridge = listed
    _click(qtbot, view, '[data-tab="abandoned"]')
    assert _texts(qtbot, view, ".group-label") == ["Abandoned"]
    _click(qtbot, view, '[data-tab="completed"]')
    assert _texts(qtbot, view, ".group-label") == ["Needs attention", "Everything else"]
    assert _texts(qtbot, view, ".group-note")[0] == "1 incomplete"


def test_a_row_draws_its_badge_with_its_tone_and_dot(qtbot, listed):
    view, _bridge = listed
    theme = get_theme_manager().get_current_theme()
    cases = {
        "2026-09-30_2": ("Not started", "neutral", "hollow"),
        "2026-09-30_1": ("In progress", "info", "half"),
        "2026-09-28_1": ("Paused", "warning", "half"),
        "2026-09-23_1": ("Stale", "warning", "half"),
        "2026-09-29_1": ("Completed", "success", "solid"),
        "2026-09-26_2": ("Incomplete", "danger", "solid"),
        "2026-09-24_1": ("Abandoned", "neutral", "solid"),
    }
    for name, (label, tone, dot) in cases.items():
        assert _text(qtbot, view, f"{_row(name)} .badge") == label
        classes = _eval(qtbot, view, f"document.querySelector('{_row(name)} .badge').className")
        assert tone in classes.split()
        dots = _eval(qtbot, view, f"document.querySelector('{_row(name)} .badge-dot').className")
        assert dot in dots.split()
    assert _style(qtbot, view, f"{_row('2026-09-30_1')} .badge", "backgroundColor") == _rgb(
        theme.status_info_bg
    )
    assert _style(qtbot, view, f"{_row('2026-09-26_2')} .badge", "color") == _rgb(
        theme.status_danger
    )


def test_the_cells_of_a_row(qtbot, listed):
    view, _bridge = listed
    row = _row("2026-09-30_1")
    assert _text(qtbot, view, f"{row} .cell-name") == "2026-09-30_1"
    assert _text(qtbot, view, f"{row} .cell-age") == "6 h"
    assert _texts(qtbot, view, f"{row} .cell-num") == ["1,197", "2,402", "9"]
    assert _text(qtbot, view, f"{row} .pack-text") == "3 / 4"
    assert _eval(qtbot, view, f"document.querySelector('{row} .cell-pack').title") == (
        "3 of 4 packing lists completed in Packing Tool"
    )
    assert _text(qtbot, view, f"{row} .cell-comment") == "Morning wave, DHL pickup 15:00"
    assert _eval(qtbot, view, f"document.querySelector('{row} .cell-comment').title") == (
        "Morning wave, DHL pickup 15:00"
    )


def test_empty_cells_draw_a_dash(qtbot, listed):
    view, _bridge = listed
    theme = get_theme_manager().get_current_theme()
    row = _row("2026-09-30_2")
    assert _texts(qtbot, view, f"{row} .none") == ["—", "—", "—"]  # blocked, packing, comment
    assert _count(qtbot, view, f"{row} .pack-track") == 0
    assert _style(qtbot, view, f"{row} .cell-comment", "color") == _rgb(theme.text_disabled)


def test_blocked_is_red_only_while_the_session_is_in_flight(qtbot, page):
    view, bridge = page
    sessions = [
        session("in-flight", blocked=9, lists=3, done=1),
        session("closed", status="completed", blocked=4, lists=2, done=2),
    ]
    _show(qtbot, view, bridge, make_state(sessions))
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, f"{_row('in-flight')} .cell-num.alert", "color") == _rgb(
        theme.status_danger
    )
    assert _count(qtbot, view, f"{_row('closed')} .cell-num.alert") == 0
    assert _texts(qtbot, view, f"{_row('closed')} .cell-num")[2] == "4"


def test_the_age_warns_before_the_auto_archive(qtbot, listed):
    view, _bridge = listed
    theme = get_theme_manager().get_current_theme()
    age = f"{_row('2026-09-05_1')} .cell-age"
    assert _text(qtbot, view, age) == "26 d"
    assert _style(qtbot, view, age, "color") == _rgb(theme.status_warning)
    assert _eval(qtbot, view, f"document.querySelector('{age}').title").endswith(
        " · Archives in 4 d"
    )
    assert _style(qtbot, view, f"{_row('2026-09-29_1')} .cell-age", "color") == _rgb(
        theme.text_secondary
    )


def test_the_packing_bar_fills_and_takes_its_tone(qtbot, listed):
    view, _bridge = listed
    theme = get_theme_manager().get_current_theme()

    def fill(name):
        selector = f"{_row(name)} .pack-fill"
        return (
            _eval(qtbot, view, f"document.querySelector('{selector}').style.width"),
            _style(qtbot, view, selector, "backgroundColor"),
        )

    assert fill("2026-09-29_1") == ("100%", _rgb(theme.status_success_dot))
    assert fill("2026-09-26_2") == ("80%", _rgb(theme.status_danger_dot))
    assert fill("2026-09-29_2") == ("67%", _rgb(theme.text_secondary))


def test_a_comment_is_drawn_as_text_never_as_markup(qtbot, page):
    view, bridge = page
    nasty = '<b>bold</b> "quoted" & <img src=x onerror=alert(1)>'
    _show(qtbot, view, bridge, make_state([session("s1", comment=nasty)]))
    assert _text(qtbot, view, f"{_row('s1')} .cell-comment") == nasty
    assert _count(qtbot, view, ".row b, .row img") == 0


def test_a_name_with_quotes_and_brackets_is_drawn_as_text_and_named_exactly(qtbot, page):
    view, bridge = page
    odd = 'copy of "2026-09-30_1" <old>'
    _show(qtbot, view, bridge, make_state([session(odd, lists=1), session("plain")]))
    assert _texts(qtbot, view, ".cell-name") == [odd, "plain"]

    _eval(
        qtbot,
        view,
        "document.querySelectorAll('.row input')[0].focus();"
        " document.querySelectorAll('.row')[0].click(); true",
    )

    assert _text(qtbot, view, "#sel-count") == "1 selected"
    assert _eval(qtbot, view, "document.activeElement.dataset.key") == f"row-{odd}"
    _click(qtbot, view, "#status-button")
    with qtbot.waitSignal(bridge.statusRequested, timeout=5000) as asked:
        _click(qtbot, view, '[data-status="completed"]')
    assert asked.args == [[odd], "completed"]


def test_a_long_comment_keeps_the_row_one_line_high(qtbot, page):
    view, bridge = page
    long = "word " * 80
    _show(qtbot, view, bridge, make_state([session("a", comment=long), session("b")]))
    heights = _json(
        qtbot, view, "Array.from(document.querySelectorAll('.row')).map(r => r.offsetHeight)"
    )
    assert heights[0] == heights[1]
    assert _eval(
        qtbot, view, "document.querySelector('.cell-comment').title"
    ) == long.strip()


# --- selection ---------------------------------------------------------------


def test_a_click_checks_the_row_and_the_bar_takes_the_headers_place(qtbot, listed):
    view, _bridge = listed
    assert _hidden(qtbot, view, "selbar") is True
    assert _hidden(qtbot, view, "head") is False

    _check(qtbot, view, "2026-09-29_2")

    assert _hidden(qtbot, view, "selbar") is False
    assert _hidden(qtbot, view, "head") is True
    assert _text(qtbot, view, "#sel-count") == "1 selected"
    assert _hidden(qtbot, view, "sel-open") is False
    assert _hidden(qtbot, view, "sel-export") is True
    assert _eval(qtbot, view, f"document.querySelector('{_row('2026-09-29_2')} input').checked") is True
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, _row("2026-09-29_2"), "backgroundColor") == _rgb(theme.selection_bg)

    _check(qtbot, view, "2026-09-26_2")
    assert _text(qtbot, view, "#sel-count") == "2 selected"
    assert _hidden(qtbot, view, "sel-open") is True
    assert _hidden(qtbot, view, "sel-export") is False

    _check(qtbot, view, "2026-09-29_2", "2026-09-26_2")
    assert _hidden(qtbot, view, "selbar") is True


def test_the_header_checkbox_checks_every_visible_row_and_the_bars_clears(qtbot, listed):
    view, _bridge = listed
    _search(qtbot, view, "09-29")
    _click(qtbot, view, "#head-check")
    assert _text(qtbot, view, "#sel-count") == "2 selected"
    assert _eval(qtbot, view, "document.getElementById('sel-check').checked") is True

    _click(qtbot, view, "#sel-check")

    assert _hidden(qtbot, view, "selbar") is True
    assert _count(qtbot, view, ".row.checked") == 0


def test_open_and_export_name_the_checked_sessions(qtbot, listed):
    view, bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    with qtbot.waitSignal(bridge.openRequested, timeout=5000) as opened:
        _click(qtbot, view, "#sel-open")
    assert opened.args == ["2026-09-29_2"]

    _check(qtbot, view, "2026-09-26_2")
    with qtbot.waitSignal(bridge.exportRequested, timeout=5000) as exported:
        _click(qtbot, view, "#sel-export")
    assert exported.args == [["2026-09-29_2", "2026-09-26_2"]]


def test_double_click_and_enter_open_the_session(qtbot, listed):
    view, bridge = listed
    with qtbot.waitSignal(bridge.openRequested, timeout=5000) as opened:
        _eval(
            qtbot,
            view,
            f"document.querySelector('{_row('2026-09-29_1')}')"
            ".dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); true",
        )
    assert opened.args == ["2026-09-29_1"]

    with qtbot.waitSignal(bridge.openRequested, timeout=5000) as opened:
        _key(qtbot, view, f"{_row('2026-09-28_1')} input", "Enter")
    assert opened.args == ["2026-09-28_1"]


def test_up_and_down_walk_the_rows_across_groups(qtbot, listed):
    view, _bridge = listed
    last_attention = f"{_row('2026-09-23_1')} input"
    _eval(qtbot, view, f"document.querySelector('{last_attention}').focus(); true")
    _key(qtbot, view, last_attention, "ArrowDown")
    assert _focused(qtbot, view) == "row-2026-09-30_2"
    _key(qtbot, view, f"{_row('2026-09-30_2')} input", "ArrowUp")
    assert _focused(qtbot, view) == "row-2026-09-23_1"


def test_a_checked_checkbox_keeps_focus_through_the_redraw(qtbot, listed):
    view, _bridge = listed
    box = f"{_row('2026-09-29_1')} input"
    _eval(qtbot, view, f"document.querySelector('{box}').focus(); true")
    _click(qtbot, view, box)
    assert _focused(qtbot, view) == "row-2026-09-29_1"
    assert _eval(qtbot, view, f"document.querySelector('{box}').checked") is True


def test_another_clients_rows_never_inherit_the_view_state(qtbot, listed):
    view, bridge = listed
    _click(qtbot, view, '[data-tab="active"]')
    _search(qtbot, view, "09-30")
    _check(qtbot, view, "2026-09-30_1")

    _show(qtbot, view, bridge, make_state(SESSIONS, client="BETA"))

    assert _eval(qtbot, view, "document.getElementById('search').value") == ""
    assert _eval(qtbot, view, "document.querySelector('[data-tab=\"all\"]').getAttribute('aria-selected')") == "true"
    assert _count(qtbot, view, ".row.checked") == 0
    assert len(_rows(qtbot, view)) == 9


def test_a_loud_reload_unchecks_and_a_quiet_one_does_not(qtbot, listed):
    view, bridge = listed
    _check(qtbot, view, "2026-09-29_1")
    _show(qtbot, view, bridge, make_state(SESSIONS[1:]))  # a quiet reload: new rows
    assert _text(qtbot, view, "#sel-count") == "1 selected"

    _show(qtbot, view, bridge, make_state(SESSIONS, loading=True))
    _show(qtbot, view, bridge, make_state(SESSIONS))

    assert _hidden(qtbot, view, "selbar") is True


def test_rows_that_leave_the_tab_stop_being_acted_on(qtbot, listed):
    view, bridge = listed
    gone = ("2026-09-29_2", "2026-09-29_1")
    _check(qtbot, view, *gone)
    _click(qtbot, view, "#status-button")

    archived = [
        dict(s, status="archived") if s["session_name"] in gone else s for s in SESSIONS
    ]
    _show(qtbot, view, bridge, make_state(archived))

    assert _hidden(qtbot, view, "selbar") is True
    assert _hidden(qtbot, view, "head") is False
    assert _hidden(qtbot, view, "status-menu") is True
    assert _text(qtbot, view, "#archived-count") == "4 archived"


# --- the Status menu ---------------------------------------------------------


def test_the_status_menu_offers_the_four_and_says_what_each_resolves_to(qtbot, listed):
    view, _bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    assert _hidden(qtbot, view, "status-menu") is True

    _click(qtbot, view, "#status-button")

    assert _hidden(qtbot, view, "status-menu") is False
    assert _eval(qtbot, view, "document.getElementById('status-button').getAttribute('aria-expanded')") == "true"
    assert _text(qtbot, view, "#status-title") == "Set status for 2026-09-29_2"
    assert _texts(qtbot, view, ".status-item .badge") == [
        "Active", "Completed", "Abandoned", "Archived",
    ]
    assert _texts(qtbot, view, ".status-note") == [
        "Shows as Not started, In progress, Paused or Stale from activity",
        "Shows as Incomplete if packing is not finished",
        "Kept on the server. Repeat-order checks ignore it",
        "Hidden from All until you choose Show",
    ]


def test_choosing_a_status_names_every_checked_session(qtbot, listed):
    view, bridge = listed
    _check(qtbot, view, "2026-09-29_2", "2026-09-26_2")
    _click(qtbot, view, "#status-button")
    assert _text(qtbot, view, "#status-title") == "Set status for 2 sessions"

    with qtbot.waitSignal(bridge.statusRequested, timeout=5000) as asked:
        _click(qtbot, view, '[data-status="archived"]')

    assert asked.args == [["2026-09-29_2", "2026-09-26_2"], "archived"]
    assert _hidden(qtbot, view, "status-menu") is True
    assert _text(qtbot, view, "#sel-count") == "2 selected"  # still checked


def test_escape_closes_the_menu_and_returns_focus_to_its_button(qtbot, listed):
    view, bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    _click(qtbot, view, "#status-button")
    _key(qtbot, view, "#status-menu", "Escape")
    assert _hidden(qtbot, view, "status-menu") is True
    assert _focused(qtbot, view) == "status-button"
    _never(qtbot, bridge.statusRequested)


def test_a_press_outside_closes_the_menu(qtbot, listed):
    view, _bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    _click(qtbot, view, "#status-button")
    _eval(
        qtbot,
        view,
        "document.getElementById('footer').dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); true",
    )
    assert _hidden(qtbot, view, "status-menu") is True


# --- the Comment popover -----------------------------------------------------


def test_the_comment_popover_opens_with_the_sessions_comment(qtbot, listed):
    view, bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    _click(qtbot, view, "#comment-button")

    assert _hidden(qtbot, view, "comment-pop") is False
    assert _text(qtbot, view, "#comment-title") == "Comment on 2026-09-29_2"
    assert _eval(qtbot, view, "document.getElementById('comment-text').value") == "Evening wave"
    assert _text(qtbot, view, "#comment-note") == "Shown in the Comment column."
    assert _focused(qtbot, view) == "comment-text"

    _eval(qtbot, view, "document.getElementById('comment-text').value = '  late van  '; true")
    with qtbot.waitSignal(bridge.commentRequested, timeout=5000) as asked:
        _click(qtbot, view, "#comment-save")

    assert asked.args == [["2026-09-29_2"], "late van"]
    assert _hidden(qtbot, view, "comment-pop") is True


def test_a_comment_on_several_starts_empty_and_says_what_it_replaces(qtbot, listed):
    view, bridge = listed
    _check(qtbot, view, "2026-09-29_2", "2026-09-26_2")
    _click(qtbot, view, "#comment-button")
    assert _text(qtbot, view, "#comment-title") == "Comment on 2 sessions"
    assert _eval(qtbot, view, "document.getElementById('comment-text').value") == ""
    assert _text(qtbot, view, "#comment-note") == (
        "Replaces the comment on 2026-09-29_2, 2026-09-26_2."
    )

    with qtbot.waitSignal(bridge.commentRequested, timeout=5000) as asked:
        _key(qtbot, view, "#comment-text", "Enter", ctrl=True)

    assert asked.args == [["2026-09-29_2", "2026-09-26_2"], ""]


def test_more_than_three_names_are_summarised(qtbot, listed):
    view, _bridge = listed
    _click(qtbot, view, "#head-check")
    _click(qtbot, view, "#comment-button")
    assert _text(qtbot, view, "#comment-note") == (
        "Replaces the comment on 2026-09-30_2, 2026-09-30_1 and 7 more."
    )


def test_cancel_and_escape_close_the_popover_without_saving(qtbot, listed):
    view, bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    _click(qtbot, view, "#comment-button")
    _click(qtbot, view, "#comment-cancel")
    assert _hidden(qtbot, view, "comment-pop") is True

    _click(qtbot, view, "#comment-button")
    _key(qtbot, view, "#comment-text", "Escape")
    assert _hidden(qtbot, view, "comment-pop") is True
    assert _focused(qtbot, view) == "comment-button"
    _never(qtbot, bridge.commentRequested)


def test_a_state_push_leaves_an_open_popover_and_its_draft_alone(qtbot, listed):
    view, bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    _click(qtbot, view, "#comment-button")
    _eval(qtbot, view, "document.getElementById('comment-text').value = 'half typed'; true")

    _show(qtbot, view, bridge, make_state(SESSIONS[1:]))

    assert _hidden(qtbot, view, "comment-pop") is False
    assert _eval(qtbot, view, "document.getElementById('comment-text').value") == "half typed"


def test_only_one_of_the_menu_and_the_popover_is_open(qtbot, listed):
    view, _bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    _click(qtbot, view, "#status-button")
    _click(qtbot, view, "#comment-button")
    assert _hidden(qtbot, view, "status-menu") is True
    assert _hidden(qtbot, view, "comment-pop") is False


def test_unchecking_the_last_row_closes_an_open_popover(qtbot, listed):
    view, _bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    _click(qtbot, view, "#comment-button")
    _check(qtbot, view, "2026-09-29_2")
    assert _hidden(qtbot, view, "comment-pop") is True


# --- footer ------------------------------------------------------------------


def test_the_footer_counts_the_archived_and_shows_them_on_request(qtbot, listed):
    view, _bridge = listed
    assert _text(qtbot, view, "#archived-count") == "2 archived"
    assert _text(qtbot, view, "#footer [data-act='toggle-archived']") == "Show"
    assert _text(qtbot, view, "#footer").endswith("Double-click a session to open it")

    _click(qtbot, view, "#footer [data-act='toggle-archived']")

    assert len(_rows(qtbot, view)) == 11
    assert _text(qtbot, view, "#archived-count") == "2 archived shown"
    assert _text(qtbot, view, "#footer [data-act='toggle-archived']") == "Hide"
    assert _text(qtbot, view, "#count") == "11 sessions"
    assert _texts(qtbot, view, ".tab .segment-count")[0] == "9"  # All never counts them

    _click(qtbot, view, "#footer [data-act='toggle-archived']")
    assert len(_rows(qtbot, view)) == 9


def test_the_archived_line_is_on_all_only_and_only_with_archived_sessions(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(SESSIONS))
    _click(qtbot, view, '[data-tab="active"]')
    assert _count(qtbot, view, "#footer [data-act]") == 0

    _show(qtbot, view, bridge, make_state(SESSIONS[:9]))
    _click(qtbot, view, '[data-tab="all"]')
    assert _count(qtbot, view, "#footer [data-act]") == 0


# --- toast -------------------------------------------------------------------


def test_an_undoable_toast_offers_undo(qtbot, listed):
    view, bridge = listed
    bridge.raise_toast("Set 2 sessions to Archived", True)
    _until_js(qtbot, view, "document.getElementById('toast').hidden === false")
    assert _text(qtbot, view, "#toast-text") == "Set 2 sessions to Archived"
    assert _hidden(qtbot, view, "toast-undo") is False

    with qtbot.waitSignal(bridge.undoRequested, timeout=5000):
        _click(qtbot, view, "#toast-undo")
    assert _hidden(qtbot, view, "toast") is True


def test_a_plain_toast_has_no_undo_and_can_be_dismissed(qtbot, listed):
    view, bridge = listed
    bridge.raise_toast("Combined stock export saved: stock.xlsx.")
    _until_js(qtbot, view, "document.getElementById('toast').hidden === false")
    assert _hidden(qtbot, view, "toast-undo") is True
    _click(qtbot, view, "#toast-dismiss")
    assert _hidden(qtbot, view, "toast") is True


# --- the card fits the page --------------------------------------------------


def test_the_card_fills_the_page_and_the_list_scrolls_inside_it(qtbot, page):
    view, bridge = page
    many = [session(f"2026-07-{d:02d}_1", age=(60 + d) * D, status="completed", lists=1, done=1) for d in range(1, 31)]
    _show(qtbot, view, bridge, make_state(SESSIONS + many))
    box = _json(
        qtbot,
        view,
        "(function () { var c = document.getElementById('card').getBoundingClientRect();"
        " var l = document.getElementById('list');"
        " return {top: c.top, bottom: c.bottom, left: c.left, right: c.right,"
        " scrolls: l.scrollHeight > l.clientHeight, page: document.documentElement.scrollHeight}; })()",
    )
    assert (box["top"], box["left"], box["right"], box["bottom"]) == (16, 24, 1142, 700)
    assert box["scrolls"] is True
    assert box["page"] == 720


def test_a_narrow_window_drops_the_count_then_scrolls_sideways(qtbot, listed):
    view, _bridge = listed
    view.resize(900, 720)
    _until_js(qtbot, view, "window.innerWidth === 900")
    assert _style(qtbot, view, "#count", "display") == "none"

    view.resize(700, 720)
    _until_js(qtbot, view, "window.innerWidth === 700")
    box = _json(
        qtbot,
        view,
        "(function () { var b = document.getElementById('browse');"
        " return {card: document.getElementById('card').offsetWidth,"
        " scrolls: b.scrollWidth > b.clientWidth}; })()",
    )
    assert box == {"card": 780, "scrolls": True}
