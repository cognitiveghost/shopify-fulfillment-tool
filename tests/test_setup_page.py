"""The Setup page, driven through a real Chromium (phase 3 spec section 5).

The page is a renderer: every test pushes a state built by setup_state() and
reads the DOM back. 1166x720 is the page a 1366x768 window gives. Never mark
skip.
"""

import json

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QApplication
from test_results_bridge import _eval, _rgb, _until_js
from test_setup_state import MEMORY, loaded, make_state

from gui.setup_bridge import PAGE, SetupView, mount_setup_page
from gui.setup_state import FileSlot, RunFacts
from gui.theme_manager import get_theme_manager
from gui.web_page import THEME_MARKER


@pytest.fixture
def page(qtbot):
    view = SetupView()
    qtbot.addWidget(view)
    bridge = mount_setup_page(view)
    view.resize(1166, 720)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def _show(qtbot, view, bridge, state):
    """Push a state and wait for the page to have drawn it."""
    before = _eval(qtbot, view, "Number(document.documentElement.dataset.renders || 0)")
    bridge.set_state(state)
    _until_js(
        qtbot, view, f"Number(document.documentElement.dataset.renders) > {before}"
    )


def _text(qtbot, view, selector):
    return _eval(
        qtbot, view, f"document.querySelector({selector!r}).textContent.trim()"
    )


def _json(qtbot, view, expr):
    """A list or an object from the page: runJavaScript hands back only scalars."""
    return json.loads(_eval(qtbot, view, f"JSON.stringify({expr})"))


def _count(qtbot, view, selector):
    return _eval(qtbot, view, f"document.querySelectorAll({selector!r}).length")


def _click(qtbot, view, selector):
    _eval(qtbot, view, f"document.querySelector({selector!r}).click(); true")


def _style(qtbot, view, selector, prop):
    return _eval(
        qtbot, view, f"getComputedStyle(document.querySelector({selector!r})).{prop}"
    )


def _disabled(qtbot, view, selector):
    return _eval(qtbot, view, f"document.querySelector({selector!r}).disabled")


def _problem_orders():
    slot = FileSlot("orders")
    slot.set_invalid(
        "/d/acme-orders-30-09.csv",
        ["Lineitem sku"],
        ["Name"],
        {"Lineitem sku": "SKU"},
        rows=1204,
        delimiter=",",
    )
    return slot


def test_the_page_carries_the_theme_marker_exactly_once():
    assert PAGE.read_text(encoding="utf-8").count(THEME_MARKER) == 1


def test_the_page_links_the_kit_before_its_own_stylesheet():
    html = PAGE.read_text(encoding="utf-8")
    assert html.index('href="../../shared/web/kit.css"') < html.index('href="setup.css"')


# --- views -------------------------------------------------------------------


def test_no_client_shows_one_panel_and_no_cards(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(client="", session=None))
    assert _eval(qtbot, view, "document.getElementById('setup').dataset.view") == "no_client"
    assert _text(qtbot, view, ".state-title") == "Choose a client to begin"
    assert _count(qtbot, view, "[data-card]") == 0
    assert _count(qtbot, view, ".state .btn") == 0


def test_no_session_offers_a_new_one_and_a_recent_one(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(session=None))
    assert _text(qtbot, view, ".state-title") == "No session open for ACME"
    assert _text(qtbot, view, ".state-text") == (
        "Start a session for today's orders, or reopen one from this client."
    )
    with qtbot.waitSignal(bridge.newSessionRequested, timeout=5000):
        _click(qtbot, view, "[data-act='new-session']")
    with qtbot.waitSignal(bridge.recentRequested, timeout=5000):
        _click(qtbot, view, "[data-act='open-recent']")
    assert "primary" in _eval(
        qtbot, view, "document.querySelector(\"[data-act='new-session']\").className"
    )


def test_unreachable_names_the_server_and_offers_the_way_out(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(connected=False, client="", session=None))
    assert _text(qtbot, view, ".state-title") == "This PC can't reach the fulfilment server"
    assert _text(qtbot, view, ".state-path") == r"\\fs01\fulfilment"
    with qtbot.waitSignal(bridge.connectionRequested, timeout=5000):
        _click(qtbot, view, "[data-act='open-connection']")


def test_the_setup_view_has_the_head_two_cards_options_and_summary(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _text(qtbot, view, ".page-title") == "New session"
    assert _text(qtbot, view, ".page-head .code") == "2026-09-30_1"
    assert _text(qtbot, view, ".page-meta") == "ACME · opened 14:02"
    assert _count(qtbot, view, "section[data-card]") == 2
    assert _count(qtbot, view, ".form-row") == 2
    assert _style(qtbot, view, ".summary", "width") == "300px"


# --- cards -------------------------------------------------------------------


def test_a_loaded_card_shows_its_badge_name_and_three_stats(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    card = "[data-card='orders']"
    assert _text(qtbot, view, f"{card} .badge") == "Loaded"
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, f"{card} .badge", "backgroundColor") == _rgb(
        theme.status_success_bg
    )
    assert _text(qtbot, view, f"{card} .file-name") == "acme-orders-30-09.csv"
    assert _json(
        qtbot,
        view,
        f"Array.from(document.querySelectorAll({card + ' .stat-v'!r})).map(e => e.textContent)",
    ) == ["1,204", "312", "Comma  ,"]
    with qtbot.waitSignal(bridge.clearRequested, timeout=5000) as caught:
        _click(qtbot, view, f"{card} [data-act='clear']")
    assert caught.args == ["orders"]


def test_a_missing_card_offers_a_file_and_a_folder(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(stock=FileSlot("stock")))
    card = "[data-card='stock']"
    assert _text(qtbot, view, f"{card} .badge") == "Missing"
    assert _text(qtbot, view, f"{card} .dropzone-text") == (
        "Drop the warehouse stock export here"
    )
    with qtbot.waitSignal(bridge.fileRequested, timeout=5000) as caught:
        _click(qtbot, view, f"{card} [data-act='choose-file']")
    assert caught.args == ["stock"]
    with qtbot.waitSignal(bridge.folderRequested, timeout=5000) as caught:
        _click(qtbot, view, f"{card} [data-act='choose-folder']")
    assert caught.args == ["stock"]


def test_memory_covering_badges_the_stock_card(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(memory=MEMORY, stock=FileSlot("stock")))
    assert _text(qtbot, view, "[data-card='stock'] .badge") == "From memory"
    assert not _disabled(qtbot, view, "[data-act='run']")


def test_a_folder_card_lists_its_parts_and_scrolls_when_there_are_many(qtbot, page):
    view, bridge = page
    parts = [{"name": f"export-{i:02d}.csv", "rows": 100 + i} for i in range(40)]
    orders = loaded(
        "orders",
        parts=parts,
        note="2 overlapping orders skipped",
        name="exports\\  ·  40 CSVs merged",
    )
    _show(qtbot, view, bridge, make_state(orders=orders))
    card = "[data-card='orders']"
    assert _count(qtbot, view, f"{card} .part") == 40
    assert _text(qtbot, view, f"{card} .part .part-rows") == "100 rows"
    assert _text(qtbot, view, f"{card} .file-note") == "2 overlapping orders skipped"
    assert _eval(
        qtbot, view, f"document.querySelector({card + ' .parts'!r}).clientHeight"
    ) <= 156
    # The options card is still on the page, under the cards, not pushed out.
    assert _eval(
        qtbot,
        view,
        "document.querySelector('.options').getBoundingClientRect().top < 720",
    )


def test_a_problem_card_explains_itself_and_links_to_the_fix(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(orders=_problem_orders()))
    card = "[data-card='orders']"
    theme = get_theme_manager().get_current_theme()
    assert _text(qtbot, view, f"{card} .badge") == "Problem"
    assert _style(qtbot, view, card, "borderTopColor") == _rgb(theme.status_danger_border)
    assert _text(qtbot, view, f"{card} .problem-title") == "No SKU column"
    assert "mapped to SKU" in _text(qtbot, view, f"{card} .banner-text")
    assert _text(qtbot, view, f"{card} [data-act='fix']") == "Open Orders mapping"
    with qtbot.waitSignal(bridge.fixRequested, timeout=5000) as caught:
        _click(qtbot, view, f"{card} [data-act='fix']")
    assert caught.args == ["orders"]


def test_a_problem_without_a_fix_has_no_link(qtbot, page):
    view, bridge = page
    orders = FileSlot("orders")
    orders.set_problem(
        "/d/exports",
        "No CSV files in this folder",
        "Choose a folder that holds the exported CSV files.",
    )
    _show(qtbot, view, bridge, make_state(orders=orders))
    assert _count(qtbot, view, "[data-card='orders'] [data-act='fix']") == 0


def test_markup_in_a_name_is_drawn_as_text(qtbot, page):
    """A file, part or column name is whatever the export called it."""
    view, bridge = page
    markup = '"><img src=x onerror="document.title=\'hit\'">'
    orders = loaded(
        "orders", parts=[{"name": markup, "rows": 1}], name=markup, note=markup
    )
    stock = FileSlot("stock")
    stock.set_invalid("/d/stock.csv", [markup], [markup], {markup: "Stock"})

    _show(qtbot, view, bridge, make_state(orders=orders, stock=stock))

    assert _count(qtbot, view, "img") == 0
    assert _eval(qtbot, view, "document.title") != "hit"
    assert _text(qtbot, view, "[data-card='orders'] .part-name") == markup
    assert markup in _text(qtbot, view, "[data-card='stock'] .banner-text")


# --- options -----------------------------------------------------------------


def test_the_switch_follows_the_state_and_asks_for_the_opposite(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    switch = "[data-act='memory']"
    assert _eval(qtbot, view, f"document.querySelector({switch!r}).getAttribute('aria-checked')") == "false"
    assert _text(qtbot, view, ".memory-state") == "Off"
    assert _count(qtbot, view, ".memory-previous") == 0
    with qtbot.waitSignal(bridge.memoryToggled, timeout=5000) as caught:
        _click(qtbot, view, switch)
    assert caught.args == [True]

    _show(qtbot, view, bridge, make_state(memory=MEMORY))
    assert _eval(qtbot, view, f"document.querySelector({switch!r}).getAttribute('aria-checked')") == "true"
    assert _text(qtbot, view, ".memory-state") == "On"
    assert _text(qtbot, view, ".memory-previous") == (
        "Previous run 2026-09-29_2 · 29 Sep 16:40 · 191 SKUs"
    )


def test_a_radio_card_reports_the_strategy_it_names(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    checked = "document.querySelector(\"[data-act='strategy'][aria-checked='true']\").dataset.value"
    assert _eval(qtbot, view, checked) == "multi_first"
    with qtbot.waitSignal(bridge.strategyChosen, timeout=5000) as caught:
        _click(qtbot, view, "[data-act='strategy'][data-value='fifo']")
    assert caught.args == ["fifo"]
    _show(qtbot, view, bridge, make_state(strategy="fifo"))
    assert _eval(qtbot, view, checked) == "fifo"


def test_an_arrow_key_moves_between_the_two_radio_cards(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _eval(
        qtbot,
        view,
        "(() => { const el = document.querySelector(\"[data-value='multi_first']\");"
        " el.focus();"
        " el.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true}));"
        " return true; })()",
    )
    assert _eval(qtbot, view, "document.activeElement.dataset.value") == "fifo"


# --- summary -----------------------------------------------------------------


def test_the_summary_reads_the_state(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    theme = get_theme_manager().get_current_theme()
    assert _text(qtbot, view, ".summary-headline") == (
        "312 orders, 1,204 lines, stock for 188 SKUs, multi-item first"
    )
    assert _style(qtbot, view, ".summary-headline", "color") == _rgb(theme.text)
    assert _json(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.summary-row')).map(r =>"
        " r.querySelector('.summary-k').textContent + ': ' + r.querySelector('.summary-v').textContent)",
    ) == [
        "Orders: 312 orders · 1,204 lines",
        "Stock: Stock file · 188 SKUs",
        "Strategy: Multi-item first",
    ]
    assert _text(qtbot, view, ".summary-reason") == "Results open when it finishes."
    assert not _disabled(qtbot, view, "[data-act='run']")
    with qtbot.waitSignal(bridge.runRequested, timeout=5000):
        _click(qtbot, view, "[data-act='run']")


def test_run_is_disabled_with_a_reason_until_the_files_are_in(qtbot, page):
    view, bridge = page
    state = make_state(orders=FileSlot("orders"), stock=FileSlot("stock"))
    _show(qtbot, view, bridge, state)
    theme = get_theme_manager().get_current_theme()
    assert _disabled(qtbot, view, "[data-act='run']")
    assert _text(qtbot, view, ".summary-reason") == (
        "Load the orders and stock files to run."
    )
    assert _style(qtbot, view, ".summary-headline", "color") == _rgb(theme.text_secondary)
    assert _style(qtbot, view, ".summary-v.muted", "color") == _rgb(theme.text_disabled)


def test_a_danger_reason_is_drawn_in_the_danger_colour(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(connected=False))
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, ".summary-reason", "color") == _rgb(theme.status_danger)
    assert _disabled(qtbot, view, "[data-act='run']")


def test_running_turns_the_summary_into_the_progress_view(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(run=RunFacts(running=True, step=2)))
    assert _text(qtbot, view, ".progress-label") == "Working · step 3 of 4"
    assert _text(qtbot, view, ".progress-step") == "Allocating stock"
    assert _count(qtbot, view, ".progress-bar") == 4
    assert _count(qtbot, view, ".progress-bar.done") == 3
    assert _text(qtbot, view, "[data-act='run']") == "Running…"
    assert _disabled(qtbot, view, "[data-act='run']")
    assert _count(qtbot, view, ".summary-reason") == 0
    with qtbot.waitSignal(bridge.cancelRequested, timeout=5000):
        _click(qtbot, view, "[data-act='cancel']")


def test_running_locks_every_input(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(run=RunFacts(running=True, step=0)))
    for selector in (
        "[data-card='orders'] [data-act='clear']",
        "[data-card='stock'] [data-act='clear']",
        "[data-act='memory']",
        "[data-act='strategy'][data-value='fifo']",
    ):
        assert _disabled(qtbot, view, selector), selector
    assert _count(qtbot, view, "[data-file-kind]") == 0


def test_cancel_is_disabled_once_saving_starts_and_while_cancelling(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(run=RunFacts(running=True, step=3)))
    assert _disabled(qtbot, view, "[data-act='cancel']")
    assert _eval(qtbot, view, "document.querySelector(\"[data-act='cancel']\").title") == (
        "Saving can't be cancelled"
    )
    _show(
        qtbot, view, bridge, make_state(run=RunFacts(running=True, step=1, cancelling=True))
    )
    assert _disabled(qtbot, view, "[data-act='cancel']")
    assert _text(qtbot, view, "[data-act='cancel']") == "Cancelling…"


def test_a_disabled_control_reports_nothing(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(orders=FileSlot("orders")))
    seen = []
    bridge.runRequested.connect(lambda: seen.append(1))
    _click(qtbot, view, "[data-act='run']")
    qtbot.wait(200)
    assert seen == []


# --- toast -------------------------------------------------------------------


def test_the_page_draws_its_own_toast_and_dismisses_it(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    bridge.raise_toast("Session 2026-09-30_1 created.")
    _until_js(qtbot, view, "!document.getElementById('toast').hidden")
    assert _text(qtbot, view, "#toast-text") == "Session 2026-09-30_1 created."
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, "#toast", "backgroundColor") == _rgb(theme.surface_inverse)
    _click(qtbot, view, "#toast-dismiss")
    assert _eval(qtbot, view, "document.getElementById('toast').hidden") is True


# --- drop --------------------------------------------------------------------


def _centre(qtbot, view, selector):
    x, y = _json(
        qtbot,
        view,
        f"(() => {{ const r = document.querySelector({selector!r}).getBoundingClientRect();"
        " return [Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2)]; })()",
    )
    return QPointF(x, y)


def _drag_to(view, point, path):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    args = (Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(view, QDragEnterEvent(point.toPoint(), *args))
    QApplication.sendEvent(view, QDragMoveEvent(point.toPoint(), *args))
    return mime


def test_a_file_dropped_on_a_card_reaches_python_with_its_kind(qtbot, page, tmp_path):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(stock=FileSlot("stock")))
    dropped = tmp_path / "stock.csv"
    dropped.write_text("x")
    point = _centre(qtbot, view, "[data-card='stock']")
    mime = _drag_to(view, point, dropped)
    _until_js(
        qtbot, view, "!!document.querySelector(\"[data-card='stock'].over\")"
    )
    with qtbot.waitSignal(view.pathDropped, timeout=5000) as caught:
        QApplication.sendEvent(
            view, QDropEvent(point, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        )
    assert caught.args == ["stock", str(dropped)]
    # Chromium would otherwise navigate to the file.
    assert _count(qtbot, view, "section[data-card]") == 2
    _until_js(qtbot, view, "!document.querySelector('.over')")


def test_a_drop_on_no_card_or_during_a_run_loads_nothing(qtbot, page, tmp_path):
    view, bridge = page
    dropped = tmp_path / "stock.csv"
    dropped.write_text("x")
    seen = []
    view.pathDropped.connect(lambda kind, path: seen.append((kind, path)))

    _show(qtbot, view, bridge, make_state())
    point = _centre(qtbot, view, ".summary")
    mime = _drag_to(view, point, dropped)
    QApplication.sendEvent(
        view, QDropEvent(point, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    )

    _show(qtbot, view, bridge, make_state(run=RunFacts(running=True, step=0)))
    point = _centre(qtbot, view, "[data-card='stock']")
    mime = _drag_to(view, point, dropped)
    QApplication.sendEvent(
        view, QDropEvent(point, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    )

    qtbot.wait(600)
    assert seen == []
    assert _count(qtbot, view, "section[data-card]") == 2
