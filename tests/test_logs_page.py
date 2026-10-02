"""The Logs page, driven through a real Chromium (phase 6 spec section 5).

The page keeps the rows it is sent and owns its view state: every test sends
rows built by to_row() through the bridge and reads the DOM back. 1166x720 is
the page a 1366x768 window gives. Never mark skip.
"""

import json
import logging
from datetime import UTC, datetime

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _rgb, _until_js

from gui.log_buffer import ACTIVITY, EXECUTION, to_row
from gui.log_entry import LogEntry
from gui.logs_bridge import PAGE, mount_logs_page
from gui.theme_manager import get_theme_manager
from gui.web_page import THEME_MARKER
from shared.theme import DARK_THEME, LIGHT_THEME

STAMP = datetime(2026, 9, 30, 14, 0, 53, 508_000, tzinfo=UTC)
TRACE = (
    "Traceback (most recent call last):\n"
    '  File "gui/tools_widget.py", line 142, in _on_run\n'
    "    self._sock.sendall(data)\n"
    "PermissionError: share is read-only"
)


def row(
    entry_id,
    message,
    level=logging.INFO,
    stream=EXECUTION,
    source="shopify_tool.core",
    trace="",
):
    return to_row(entry_id, LogEntry(STAMP, level, source, message, trace), stream)


def sample():
    """Six rows: four Execution (one warning, one error with a traceback), two Activity."""
    return [
        row(0, "Scanned order #48254"),
        row(1, "New session created: 2026-09-30_1", stream=ACTIVITY, source="Session"),
        row(
            2, "Stock file is 19 h old", logging.WARNING, source="shopify_tool.analysis"
        ),
        row(
            3,
            "Save failed — PermissionError: share is read-only",
            logging.ERROR,
            source="gui.tools_widget",
            trace=TRACE,
        ),
        row(4, "Generated: picklist", stream=ACTIVITY, source="Report"),
        row(5, "Label printer ready", source="shopify_tool.pdf_processor"),
    ]


def many(n, start=0):
    return [row(start + i, f"Scanned order #{start + i}") for i in range(n)]


def _mount(qtbot, wrap=False, capacity=5000):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_logs_page(view, wrap=wrap, capacity=capacity)
    view.resize(1166, 720)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


@pytest.fixture
def page(qtbot):
    return _mount(qtbot)


def _renders(qtbot, view):
    return _eval(qtbot, view, "Number(document.documentElement.dataset.renders || 0)")


def _drawn(qtbot, view, before):
    _until_js(
        qtbot, view, f"Number(document.documentElement.dataset.renders) > {before}"
    )


def _send(qtbot, view, bridge, rows):
    """Send a batch and wait for the page to have drawn it."""
    before = _renders(qtbot, view)
    bridge.send(rows)
    _drawn(qtbot, view, before)


def _do(qtbot, view, script):
    """Run a statement in the page and wait for the redraw it causes."""
    before = _renders(qtbot, view)
    _eval(qtbot, view, f"(function () {{ {script}; return true; }})()")
    _drawn(qtbot, view, before)


def _click(qtbot, view, selector):
    _do(qtbot, view, f"document.querySelector({selector!r}).click()")


def _search(qtbot, view, text):
    _do(
        qtbot,
        view,
        "const el = document.querySelector('#search');"
        f" el.value = {json.dumps(text)};"
        " el.dispatchEvent(new Event('input', { bubbles: true }))",
    )


def _json(qtbot, view, expr):
    """A list or an object from the page: runJavaScript hands back only scalars."""
    return json.loads(_eval(qtbot, view, f"JSON.stringify({expr})"))


def _text(qtbot, view, selector):
    return _eval(
        qtbot, view, f"document.querySelector({selector!r}).textContent.trim()"
    )


def _hidden(qtbot, view, selector):
    return _eval(qtbot, view, f"document.querySelector({selector!r}).hidden")


def _shown_ids(qtbot, view):
    return _json(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('#list .row'))"
        ".filter((el) => !el.hidden).map((el) => Number(el.dataset.id))",
    )


def _counts(qtbot, view):
    return _json(
        qtbot,
        view,
        "Object.fromEntries(Array.from(document.querySelectorAll('#bands .segment'))"
        ".map((el) => [el.dataset.key, Number(el.querySelector('.segment-count').textContent)]))",
    )


def _at_end(qtbot, view):
    return _eval(
        qtbot,
        view,
        "(function () { const l = document.querySelector('#list');"
        " return l.scrollHeight - l.scrollTop - l.clientHeight <= 4; })()",
    )


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


STREAM = '#streams [data-key="{}"]'
BAND = '#bands [data-key="{}"]'
ERROR_ROW = '#list .row[data-id="3"]'


# --- the files ----------------------------------------------------------------


def test_the_page_carries_the_theme_marker_exactly_once():
    assert PAGE.read_text(encoding="utf-8").count(THEME_MARKER) == 1


def test_the_page_links_the_kit_before_its_own_stylesheet():
    html = PAGE.read_text(encoding="utf-8")
    assert html.index('href="kit.css"') < html.index('href="logs.css"')


# --- start --------------------------------------------------------------------


def test_the_page_says_when_it_is_listening(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_logs_page(view)
    started = _caught(bridge.started)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    qtbot.waitUntil(lambda: started == [()])


def test_with_no_entries_the_page_says_so_and_save_is_off(qtbot, page):
    view, _ = page
    assert _hidden(qtbot, view, "#empty") is False
    assert _hidden(qtbot, view, "#list") is True
    assert _text(qtbot, view, "#empty-title") == "No entries yet"
    assert _hidden(qtbot, view, "#empty-text") is True
    assert _hidden(qtbot, view, "#clear-search") is True
    assert _hidden(qtbot, view, "#show-all") is True
    assert _eval(qtbot, view, "document.querySelector('#save').disabled") is True
    assert _text(qtbot, view, "#count") == "0 entries"
    assert _hidden(qtbot, view, "#paused") is True


# --- rows ---------------------------------------------------------------------


def test_rows_are_drawn_oldest_first_with_their_cells(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    assert _shown_ids(qtbot, view) == [0, 1, 2, 3, 4, 5]
    assert _hidden(qtbot, view, "#empty") is True
    assert _text(qtbot, view, "#count") == "6 entries"
    cells = _json(
        qtbot,
        view,
        f"Array.from(document.querySelectorAll({ERROR_ROW + ' > span'!r}))"
        ".map((el) => [el.className, el.textContent, el.title])",
    )
    assert cells == [
        ["cell-chev", "", ""],
        ["cell-time mono", "14:00:53.508", "2026-09-30 14:00:53.508"],
        ["cell-level", "Error", ""],
        ["cell-from", "Execution", ""],
        ["cell-source mono", "tools_widget", "gui.tools_widget"],
        ["cell-message", "Save failed — PermissionError: share is read-only", ""],
    ]


def test_only_warning_and_error_carry_a_tone(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    badges = _json(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('#list .badge')).map((el) => el.className)",
    )
    assert badges == [
        "badge neutral",
        "badge neutral",
        "badge warning",
        "badge danger",
        "badge neutral",
        "badge neutral",
    ]
    assert _eval(
        qtbot,
        view,
        f"getComputedStyle(document.querySelector({ERROR_ROW + ' .cell-message'!r})).color",
    ) == _rgb(LIGHT_THEME.status_danger)
    assert _eval(
        qtbot,
        view,
        "getComputedStyle(document.querySelector('#list .row[data-id=\"2\"] .cell-message')).color",
    ) == _rgb(LIGHT_THEME.text)


def test_only_a_row_with_a_traceback_is_a_button(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    assert _json(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('#list .row[role=\"button\"]'))"
        ".map((el) => [Number(el.dataset.id), el.tabIndex, el.getAttribute('aria-expanded'),"
        " el.querySelectorAll('.cell-chev svg').length])",
    ) == [[3, 0, "false", 1]]
    assert (
        _eval(qtbot, view, "document.querySelectorAll('#list .cell-chev svg').length")
        == 1
    )


def test_a_message_with_markup_in_it_is_drawn_as_text(qtbot, page):
    view, bridge = page
    hostile = "<img src=x onerror=\"document.title='pwned'\"><b>bold</b>"
    _send(
        qtbot,
        view,
        bridge,
        [row(0, hostile, source="<i>x</i>.<u>y</u>", trace="<s>tb</s>")],
    )
    assert _text(qtbot, view, "#list .cell-message") == hostile
    assert _text(qtbot, view, "#list .cell-source") == "<u>y</u>"
    _click(qtbot, view, '#list .row[data-id="0"]')
    assert _text(qtbot, view, "#list .tb-text") == "<s>tb</s>"
    assert (
        _eval(
            qtbot,
            view,
            "document.querySelectorAll('#list img, #list b, #list u, #list s').length",
        )
        == 0
    )
    assert _eval(qtbot, view, "document.title") == "Logs"


def test_a_batch_sent_twice_is_drawn_once(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _send(qtbot, view, bridge, sample())
    assert _shown_ids(qtbot, view) == [0, 1, 2, 3, 4, 5]


def test_the_page_keeps_the_newest_rows_of_each_stream(qtbot):
    view, bridge = _mount(qtbot, capacity=3)
    first = [row(0, "kept", stream=ACTIVITY, source="Session")] + many(5, start=1)
    _send(qtbot, view, bridge, first)
    assert _shown_ids(qtbot, view) == [0, 3, 4, 5]
    assert _text(qtbot, view, "#count") == "4 entries"
    _send(qtbot, view, bridge, many(1, start=6))
    assert _shown_ids(qtbot, view) == [0, 4, 5, 6]


def test_five_thousand_rows_arrive_in_one_batch(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, many(5000))
    assert _eval(qtbot, view, "document.querySelectorAll('#list .row').length") == 5000
    assert _text(qtbot, view, "#count") == "5000 entries"
    assert _at_end(qtbot, view) is True


# --- source, level and search -------------------------------------------------


def test_the_level_counts_follow_the_source(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    assert _counts(qtbot, view) == {"all": 6, "info": 4, "warning": 1, "error": 1}
    assert (
        _eval(
            qtbot, view, "document.querySelectorAll('#streams .segment-count').length"
        )
        == 0
    )
    _click(qtbot, view, STREAM.format("Activity"))
    assert _counts(qtbot, view) == {"all": 2, "info": 2, "warning": 0, "error": 0}
    assert _shown_ids(qtbot, view) == [1, 4]
    assert _text(qtbot, view, "#count") == "2 of 6 entries"


def test_the_error_count_is_toned_only_above_zero(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    alert = "document.querySelector('#bands [data-key=\"error\"] .segment-count').classList.contains('alert')"
    assert _eval(qtbot, view, alert) is True
    _click(qtbot, view, STREAM.format("Activity"))
    assert _eval(qtbot, view, alert) is False
    assert (
        _eval(qtbot, view, "document.querySelectorAll('#bands .seg-dot').length") == 2
    )


def test_one_source_drops_the_from_column(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    from_cell = "getComputedStyle(document.querySelector('{} .cell-from')).display"
    assert _eval(qtbot, view, from_cell.format(".list-head")) == "block"
    _click(qtbot, view, STREAM.format("Execution"))
    assert _shown_ids(qtbot, view) == [0, 2, 3, 5]
    assert _eval(qtbot, view, from_cell.format(".list-head")) == "none"
    assert _eval(qtbot, view, from_cell.format(ERROR_ROW)) == "none"
    _click(qtbot, view, STREAM.format("all"))
    assert _eval(qtbot, view, from_cell.format(ERROR_ROW)) == "block"


def test_a_level_is_one_band_not_a_floor(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _click(qtbot, view, BAND.format("warning"))
    assert _shown_ids(qtbot, view) == [2]
    assert _text(qtbot, view, "#count") == "1 of 6 entries"
    _click(qtbot, view, BAND.format("info"))
    assert _shown_ids(qtbot, view) == [0, 1, 4, 5]
    checked = "Array.from(document.querySelectorAll('#bands .segment')).map((el) => [el.getAttribute('aria-checked'), el.tabIndex])"
    assert _json(qtbot, view, checked) == [
        ["false", -1],
        ["true", 0],
        ["false", -1],
        ["false", -1],
    ]


def test_search_reads_the_message_and_the_source_but_not_the_traceback(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _search(qtbot, view, "  PICKLIST ")
    assert _shown_ids(qtbot, view) == [4]
    _search(qtbot, view, "gui.tools")
    assert _shown_ids(qtbot, view) == [3]
    assert _counts(qtbot, view) == {"all": 1, "info": 0, "warning": 0, "error": 1}
    _search(qtbot, view, "sendall")
    assert _shown_ids(qtbot, view) == []
    # The search text is plain text, never a pattern.
    _search(qtbot, view, ".*")
    assert _shown_ids(qtbot, view) == []
    _search(qtbot, view, "#48254")
    assert _shown_ids(qtbot, view) == [0]


def test_the_arrow_keys_move_along_a_control_and_choose(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    press = (
        "const el = document.querySelector('#bands [aria-checked=\"true\"]'); el.focus();"
        " el.dispatchEvent(new KeyboardEvent('keydown', {{ key: '{}', bubbles: true }}))"
    )
    _do(qtbot, view, press.format("ArrowLeft"))  # wraps from All to Error
    assert _shown_ids(qtbot, view) == [3]
    assert _eval(qtbot, view, "document.activeElement.dataset.key") == "error"
    _do(qtbot, view, press.format("ArrowRight"))
    assert _shown_ids(qtbot, view) == [0, 1, 2, 3, 4, 5]
    assert _eval(qtbot, view, "document.activeElement.dataset.key") == "all"


# --- empty states -------------------------------------------------------------


def test_a_search_that_finds_nothing_says_where_it_looked(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _search(qtbot, view, "zebra")
    assert _text(qtbot, view, "#empty-title") == "No entries match"
    assert _text(qtbot, view, "#empty-text") == (
        "Nothing contains “zebra” in its message or source."
    )
    assert _hidden(qtbot, view, "#clear-search") is False
    assert _hidden(qtbot, view, "#show-all") is True
    assert _eval(qtbot, view, "document.querySelector('#save').disabled") is True

    _click(qtbot, view, BAND.format("error"))
    _click(qtbot, view, STREAM.format("Execution"))
    assert _text(qtbot, view, "#empty-text") == (
        "Nothing in Error Execution contains “zebra” in its message or source."
    )
    assert _hidden(qtbot, view, "#show-all") is False

    _click(qtbot, view, "#clear-search")
    assert _shown_ids(qtbot, view) == [3]
    assert _eval(qtbot, view, "document.querySelector('#search').value") == ""


def test_a_filter_with_nothing_in_it_offers_to_show_everything(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _click(qtbot, view, STREAM.format("Activity"))
    _click(qtbot, view, BAND.format("warning"))
    assert _text(qtbot, view, "#empty-title") == "No entries match"
    assert _text(qtbot, view, "#empty-text") == "No Warning Activity entries yet."
    assert _hidden(qtbot, view, "#clear-search") is True
    _click(qtbot, view, "#show-all")
    assert _shown_ids(qtbot, view) == [0, 1, 2, 3, 4, 5]
    assert (
        _eval(
            qtbot,
            view,
            "document.querySelector('#streams [aria-checked=\"true\"]').dataset.key",
        )
        == "all"
    )
    assert (
        _eval(
            qtbot,
            view,
            "document.querySelector('#bands [aria-checked=\"true\"]').dataset.key",
        )
        == "all"
    )


# --- traceback ----------------------------------------------------------------


def test_a_click_opens_the_traceback_under_its_row_and_another_closes_it(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _click(qtbot, view, ERROR_ROW)
    assert (
        _eval(
            qtbot,
            view,
            f"document.querySelector({ERROR_ROW!r}).nextElementSibling.className",
        )
        == "tb"
    )
    assert (
        _eval(qtbot, view, f"document.querySelector({ERROR_ROW!r}).className")
        == "row grid error has-tb open"
    )
    assert (
        _eval(
            qtbot,
            view,
            f"document.querySelector({ERROR_ROW!r}).getAttribute('aria-expanded')",
        )
        == "true"
    )
    assert (
        _eval(qtbot, view, "document.querySelector('#list .tb-text').textContent")
        == TRACE
    )
    assert _json(
        qtbot,
        view,
        "Array.from(document.querySelector('#list .tb-head').children).map((el) => el.textContent)",
    ) == ["Traceback", "gui.tools_widget", "", "Copy"]
    _click(qtbot, view, ERROR_ROW)
    assert _eval(qtbot, view, "document.querySelectorAll('#list .tb').length") == 0
    assert (
        _eval(qtbot, view, f"document.querySelector({ERROR_ROW!r}).className")
        == "row grid error has-tb"
    )


def test_enter_opens_a_focused_row_and_a_plain_row_ignores_a_click(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _do(
        qtbot,
        view,
        f"const el = document.querySelector({ERROR_ROW!r}); el.focus();"
        " el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))",
    )
    assert _eval(qtbot, view, "document.querySelectorAll('#list .tb').length") == 1
    before = _renders(qtbot, view)
    _eval(
        qtbot, view, "document.querySelector('#list .row[data-id=\"0\"]').click(); true"
    )
    qtbot.wait(100)
    assert _renders(qtbot, view) == before
    assert _eval(qtbot, view, "document.querySelectorAll('#list .tb').length") == 1


def test_a_click_that_ends_a_selection_does_not_toggle(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _eval(
        qtbot,
        view,
        f"window.getSelection().selectAllChildren(document.querySelector({ERROR_ROW + ' .cell-message'!r}));"
        f" document.querySelector({ERROR_ROW!r}).click(); true",
    )
    qtbot.wait(100)
    assert _eval(qtbot, view, "document.querySelectorAll('#list .tb').length") == 0


def test_copy_names_the_entry_to_python_and_leaves_the_row_open(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _click(qtbot, view, ERROR_ROW)
    copied = _caught(bridge.copyRequested)
    _eval(qtbot, view, "document.querySelector('#list [data-copy]').click(); true")
    qtbot.waitUntil(lambda: copied == [(3,)])
    assert _eval(qtbot, view, "document.querySelectorAll('#list .tb').length") == 1


def test_a_filter_that_hides_a_row_hides_its_open_traceback(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _click(qtbot, view, ERROR_ROW)
    _click(qtbot, view, BAND.format("info"))
    assert _hidden(qtbot, view, "#list .tb") is True
    _click(qtbot, view, BAND.format("all"))
    assert _hidden(qtbot, view, "#list .tb") is False


# --- follow -------------------------------------------------------------------


def _scroll_up(qtbot, view):
    _eval(qtbot, view, "document.querySelector('#list').scrollTop = 0; true")
    _until_js(qtbot, view, "document.querySelector('#follow').checked === false")


def test_follow_keeps_the_list_at_its_end(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, many(200))
    assert _at_end(qtbot, view) is True
    _send(qtbot, view, bridge, many(50, start=200))
    assert _at_end(qtbot, view) is True
    assert _eval(qtbot, view, "document.querySelector('#follow').checked") is True
    assert _hidden(qtbot, view, "#paused") is True


def test_scrolling_up_pauses_and_counts_what_arrives_below(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, many(200))
    _scroll_up(qtbot, view)
    assert _hidden(qtbot, view, "#paused") is False
    assert _text(qtbot, view, "#paused-text") == "Paused while scrolled up"

    _send(qtbot, view, bridge, many(1, start=200))
    assert _text(qtbot, view, "#paused-text") == "1 new entry below"
    _send(qtbot, view, bridge, many(2, start=201))
    assert _text(qtbot, view, "#paused-text") == "3 new entries below"
    assert _eval(qtbot, view, "document.querySelector('#list').scrollTop") == 0

    _click(qtbot, view, "#jump")
    assert _at_end(qtbot, view) is True
    assert _eval(qtbot, view, "document.querySelector('#follow').checked") is True
    assert _hidden(qtbot, view, "#paused") is True


def test_the_count_below_is_of_the_entries_the_filter_shows(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, many(200))
    _click(qtbot, view, BAND.format("info"))
    _scroll_up(qtbot, view)
    _send(
        qtbot,
        view,
        bridge,
        [
            row(200, "shown"),
            row(201, "not shown", logging.ERROR),
            row(202, "shown too"),
        ],
    )
    assert _text(qtbot, view, "#paused-text") == "2 new entries below"


def test_scrolling_back_to_the_end_follows_again(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, many(200))
    _scroll_up(qtbot, view)
    _send(qtbot, view, bridge, many(1, start=200))
    _eval(
        qtbot,
        view,
        "(function () { const l = document.querySelector('#list'); l.scrollTop = l.scrollHeight; return true; })()",
    )
    _until_js(qtbot, view, "document.querySelector('#follow').checked === true")
    assert _hidden(qtbot, view, "#paused") is True
    _scroll_up(qtbot, view)
    assert _text(qtbot, view, "#paused-text") == "Paused while scrolled up"


def test_a_filter_change_follows_again(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, many(200))
    _scroll_up(qtbot, view)
    _click(qtbot, view, STREAM.format("Execution"))
    assert _eval(qtbot, view, "document.querySelector('#follow').checked") is True
    assert _at_end(qtbot, view) is True


def test_unticking_follow_stops_it_and_ticking_it_jumps(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, many(200))
    _click(qtbot, view, "#follow")
    assert _eval(qtbot, view, "document.querySelector('#follow').checked") is False
    _eval(qtbot, view, "document.querySelector('#list').scrollTop = 0; true")
    _send(qtbot, view, bridge, many(1, start=200))
    assert _eval(qtbot, view, "document.querySelector('#list').scrollTop") == 0
    _click(qtbot, view, "#follow")
    assert _at_end(qtbot, view) is True


def test_opening_a_row_stops_follow(qtbot, page):
    view, bridge = page
    _send(
        qtbot,
        view,
        bridge,
        many(200) + [row(200, "Save failed", logging.ERROR, trace=TRACE)],
    )
    _click(qtbot, view, '#list .row[data-id="200"]')
    assert _eval(qtbot, view, "document.querySelector('#follow').checked") is False
    assert _text(qtbot, view, "#paused-text") == "Paused while scrolled up"


# --- wrap ---------------------------------------------------------------------


def test_wrap_starts_as_this_pc_left_it_and_tells_python_when_it_changes(qtbot):
    view, bridge = _mount(qtbot, wrap=True)
    _send(qtbot, view, bridge, sample())
    assert _eval(qtbot, view, "document.querySelector('#wrap').checked") is True
    assert (
        _eval(qtbot, view, "document.querySelector('#list').classList.contains('wrap')")
        is True
    )
    assert (
        _eval(
            qtbot,
            view,
            "getComputedStyle(document.querySelector('#list .cell-message')).whiteSpace",
        )
        == "pre-wrap"
    )
    wraps = _caught(bridge.wrapRequested)
    _click(qtbot, view, "#wrap")
    qtbot.waitUntil(lambda: wraps == [(False,)])
    assert (
        _eval(qtbot, view, "document.querySelector('#list').classList.contains('wrap')")
        is False
    )
    assert (
        _eval(
            qtbot,
            view,
            "getComputedStyle(document.querySelector('#list .cell-message')).whiteSpace",
        )
        == "nowrap"
    )


def test_a_row_is_twenty_six_pixels_and_a_wrapped_long_one_is_taller(qtbot, page):
    view, bridge = page
    _send(
        qtbot,
        view,
        bridge,
        [row(0, "word " * 200), row(1, "first line\nsecond line"), row(2, "short")],
    )
    heights = (
        "Array.from(document.querySelectorAll('#list .row'))"
        ".map((el) => el.getBoundingClientRect().height)"
    )
    assert _json(qtbot, view, heights) == [26, 26, 26]
    _click(qtbot, view, "#wrap")
    long, two_lines, short = _json(qtbot, view, heights)
    assert long > two_lines > short == 26


# --- save ---------------------------------------------------------------------


def test_save_sends_the_ids_of_the_rows_shown(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    saves = _caught(bridge.saveRequested)
    _click(qtbot, view, STREAM.format("Execution"))
    _eval(qtbot, view, "document.querySelector('#save').click(); true")
    qtbot.waitUntil(lambda: saves == [([0, 2, 3, 5],)])
    assert _text(qtbot, view, "#save") == "Save as text"
    assert _eval(qtbot, view, "document.querySelector('#save').title") == (
        "Save shown entries as text  Ctrl+S"
    )


def test_ctrl_s_saves_and_does_nothing_when_no_row_is_shown(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    saves = _caught(bridge.saveRequested)
    press = (
        "document.dispatchEvent(new KeyboardEvent('keydown',"
        " { key: 's', ctrlKey: true, bubbles: true, cancelable: true })); true"
    )
    _eval(qtbot, view, press)
    qtbot.waitUntil(lambda: saves == [([0, 1, 2, 3, 4, 5],)])
    _search(qtbot, view, "zebra")
    _eval(qtbot, view, press)
    qtbot.wait(200)
    assert len(saves) == 1


# --- toast and theme ----------------------------------------------------------


def test_a_toast_is_drawn_in_the_page_and_can_be_dismissed(qtbot, page):
    view, bridge = page
    assert _hidden(qtbot, view, "#toast") is True
    bridge.raise_toast("Traceback copied")
    _until_js(qtbot, view, "document.querySelector('#toast').hidden === false")
    assert _text(qtbot, view, "#toast-text") == "Traceback copied"
    _eval(qtbot, view, "document.querySelector('#toast-dismiss').click(); true")
    assert _hidden(qtbot, view, "#toast") is True


def test_a_theme_switch_repaints_the_rows(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    get_theme_manager().set_theme(
        "dark"
    )  # conftest's reset_theme_and_density restores light
    _until_js(
        qtbot,
        view,
        f"getComputedStyle(document.body).backgroundColor === '{_rgb(DARK_THEME.surface_sunken)}'",
    )
    assert _eval(
        qtbot,
        view,
        f"getComputedStyle(document.querySelector({ERROR_ROW + ' .cell-message'!r})).color",
    ) == _rgb(DARK_THEME.status_danger)


def test_a_smaller_window_keeps_a_following_list_at_its_end(qtbot, page):
    """The Logs tab is usually hidden while entries arrive, and sized when shown."""
    view, bridge = page
    _send(qtbot, view, bridge, many(200))
    view.resize(1166, 420)
    _until_js(qtbot, view, "window.innerHeight < 500")
    _until_js(
        qtbot,
        view,
        "(function () { const l = document.querySelector('#list');"
        " return l.scrollHeight - l.scrollTop - l.clientHeight <= 4; })()",
    )
    assert _eval(qtbot, view, "document.querySelector('#follow').checked") is True
