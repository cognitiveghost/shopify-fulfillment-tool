"""The Tools page, driven through a real Chromium (phase 5 spec section 5).

The page is a renderer: every test pushes a state built by tools_state() and
reads the DOM back. 1166x720 is the page a 1366x768 window gives. Never mark
skip.
"""

import json

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _rgb, _until_js
from test_tools_state import (
    BAD_CSV,
    DRIVER,
    PRINTERS,
    ZPL,
    barcode,
    make_state,
    reference,
)

from gui.theme_manager import get_theme_manager
from gui.tools_bridge import PAGE, mount_tools_page
from gui.tools_state import (
    BarcodeFacts,
    PackingList,
    PrintFacts,
    ReferenceFacts,
    ToolRun,
)
from gui.web_page import THEME_MARKER
from shopify_tool.pdf_processor import SAVING, STAMPING


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_tools_page(view)
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


def _attr(qtbot, view, selector, name):
    return _eval(
        qtbot, view, f"document.querySelector({selector!r}).getAttribute({name!r})"
    )


def _change(qtbot, view, selector, value):
    """Type `value` into a field and commit it, as blur or Enter would."""
    _eval(
        qtbot,
        view,
        "(function () {"
        f" const el = document.querySelector({selector!r});"
        f" el.value = {json.dumps(value)};"
        " el.dispatchEvent(new Event('change', { bubbles: true }));"
        " return true; })()",
    )


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


def _key(name):
    return f'[data-key="{name}"]'


REF = '[data-tool="reference"]'
BAR = '[data-tool="barcode"]'


# --- the files ----------------------------------------------------------------


def test_the_page_carries_the_theme_marker_exactly_once():
    assert PAGE.read_text(encoding="utf-8").count(THEME_MARKER) == 1


def test_the_page_links_the_kit_before_its_own_stylesheet():
    html = PAGE.read_text(encoding="utf-8")
    assert html.index('href="kit.css"') < html.index('href="tools.css"')


# --- frame --------------------------------------------------------------------


def test_with_a_session_the_head_shows_its_chip_and_there_is_no_banner(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _text(qtbot, view, ".page-title") == "Tools"
    assert _text(qtbot, view, ".page-head .code") == "2026-09-30_1"
    assert _text(qtbot, view, ".page-meta") == "ACME · opened 14:02"
    assert _count(qtbot, view, "[data-banner]") == 0
    assert _count(qtbot, view, ".tool-card") == 2
    assert _text(qtbot, view, f"{REF} .tool-title") == "Reference labels"
    assert _text(qtbot, view, f"{BAR} .tool-title") == "Barcode labels"


def test_with_no_session_one_banner_explains_and_offers_the_two_ways_in(qtbot, page):
    view, bridge = page
    _show(
        qtbot,
        view,
        bridge,
        make_state(session=None, reference=ReferenceFacts(), barcode=BarcodeFacts()),
    )
    assert _count(qtbot, view, ".page-head .code") == 0
    assert _text(qtbot, view, "[data-banner] .banner-title") == (
        "Open a session to use these tools"
    )
    new, recent = _caught(bridge.newSessionRequested), _caught(bridge.recentRequested)
    _click(qtbot, view, _key("new-session"))
    _click(qtbot, view, _key("open-recent"))
    qtbot.waitUntil(lambda: new == [()] and recent == [()])


def test_with_no_session_the_fields_go_quiet_and_print_mode_stays_live(qtbot, page):
    view, bridge = page
    _show(
        qtbot,
        view,
        bridge,
        make_state(session=None, reference=ReferenceFacts(), barcode=BarcodeFacts()),
    )
    for key in (
        "pdf-choose",
        "csv-choose",
        "reference-folder",
        "reference-open_pdf",
        "barcode-list",
        "barcode-refresh",
        "barcode-qr",
        "barcode-open_pdf",
        "reference-run",
        "barcode-run",
        "reference-print-labels",
        "barcode-print-labels",
    ):
        assert _disabled(qtbot, view, _key(key)) is True, key
    for key in (
        "reference-mode-driver",
        "reference-mode-raw_zpl",
        "reference-printer",
        "barcode-printer",
        "barcode-fold",
    ):
        assert _disabled(qtbot, view, _key(key)) is False, key
    assert _text(qtbot, view, f"{REF} .path") == "Session folder"
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, f"{REF} .path", "color") == _rgb(theme.text_disabled)
    assert _text(qtbot, view, f"{BAR} .select-value") == "No packing lists"
    assert _text(qtbot, view, f"{REF} .tool-reason") == ""


def test_the_cards_sit_side_by_side_and_stack_when_the_page_is_narrow(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    tops = "Array.from(document.querySelectorAll('.tool-card')).map(c => c.getBoundingClientRect().top)"
    lefts = "Array.from(document.querySelectorAll('.tool-card')).map(c => c.getBoundingClientRect().left)"
    top = _json(qtbot, view, tops)
    left = _json(qtbot, view, lefts)
    assert top[0] == top[1]
    assert left[0] < left[1]
    # Nothing is wider than the page.
    assert _eval(qtbot, view, "document.getElementById('tools').scrollWidth <= window.innerWidth")

    view.resize(800, 720)
    _until_js(
        qtbot,
        view,
        "(function () { const c = document.querySelectorAll('.tool-card');"
        " return c[0].getBoundingClientRect().top < c[1].getBoundingClientRect().top; })()",
    )
    left = _json(qtbot, view, lefts)
    assert left[0] == left[1]
    assert _eval(qtbot, view, "document.getElementById('tools').scrollWidth <= window.innerWidth")


def test_the_tool_card_row_is_the_kit_row_with_a_narrow_quiet_label(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _style(qtbot, view, f"{REF} .form-row", "gridTemplateColumns").startswith("112px ")
    assert _style(qtbot, view, f"{REF} .form-label", "fontWeight") == "400"
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, f"{REF} .form-label", "color") == _rgb(theme.text_secondary)


# --- reference labels ---------------------------------------------------------


def test_with_nothing_picked_each_file_row_offers_choose(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(reference=reference(pdf=None, csv=None)))
    assert _text(qtbot, view, _key("pdf-choose")) == "Choose PDF…"
    assert _text(qtbot, view, _key("csv-choose")) == "Choose CSV…"
    seen = _caught(bridge.fileRequested)
    _click(qtbot, view, _key("pdf-choose"))
    _click(qtbot, view, _key("csv-choose"))
    qtbot.waitUntil(lambda: seen == [("pdf",), ("csv",)])


def test_a_picked_file_shows_its_name_and_count_and_can_be_replaced(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _text(qtbot, view, '[data-row="pdf"] .file-name') == "dhl-labels-30-09.pdf"
    assert _text(qtbot, view, '[data-row="pdf"] .file-meta') == "120 pages"
    assert _text(qtbot, view, '[data-row="csv"] .file-meta') == "120 rows"
    assert _count(qtbot, view, f"{REF} .banner") == 0
    seen = _caught(bridge.clearRequested)
    _click(qtbot, view, _key("csv-clear"))
    qtbot.waitUntil(lambda: seen == [("csv",)])


def test_a_bad_csv_is_flagged_under_its_own_field(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(reference=reference(csv=BAD_CSV)))
    theme = get_theme_manager().get_current_theme()
    assert _count(qtbot, view, '[data-row="csv"] .banner.danger') == 1
    assert _count(qtbot, view, '[data-row="pdf"] .banner') == 0
    assert _text(qtbot, view, '[data-row="csv"] .problem-title') == (
        "This CSV has no usable rows"
    )
    assert _text(qtbot, view, '[data-row="csv"] .file-meta') == "Problem"
    assert _style(qtbot, view, '[data-row="csv"] .file-meta', "color") == _rgb(
        theme.status_danger
    )
    assert _style(qtbot, view, '[data-row="csv"] .tool-line .glyph', "color") == _rgb(
        theme.status_danger
    )
    assert _text(qtbot, view, f"{REF} .tool-reason") == "Fix the mapping CSV to process."
    assert _style(qtbot, view, f"{REF} .tool-reason", "color") == _rgb(theme.status_danger)
    assert _disabled(qtbot, view, _key("reference-run")) is True
    # The card's own edge does not change (the mockup flags the field only).
    assert _style(qtbot, view, REF, "borderTopColor") != _rgb(theme.status_danger_border)
    seen = _caught(bridge.fileRequested)
    _click(qtbot, view, _key("csv-again"))
    qtbot.waitUntil(lambda: seen == [("csv",)])


def test_the_output_folder_row_and_its_checkbox(qtbot, page):
    view, bridge = page
    state = make_state()
    _show(qtbot, view, bridge, state)
    assert _text(qtbot, view, f"{REF} .path") == state["reference"]["folder"]["text"]
    assert _attr(qtbot, view, f"{REF} .path", "title") == state["reference"]["folder"]["title"]
    folder, option = _caught(bridge.folderRequested), _caught(bridge.optionChanged)
    _click(qtbot, view, _key("reference-folder"))
    _click(qtbot, view, _key("reference-open_pdf"))
    qtbot.waitUntil(lambda: folder == [()] and option == [("reference", "open_pdf", False)])


# --- barcode labels -----------------------------------------------------------


def test_the_packing_list_select_shows_the_list_and_its_count(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _text(qtbot, view, f"{_key('barcode-list')} .select-value") == "DHL"
    assert _text(qtbot, view, f"{_key('barcode-list')} .select-meta") == "120 Fulfillable"
    assert _attr(qtbot, view, _key("barcode-list"), "aria-expanded") == "false"
    assert _count(qtbot, view, f"{BAR} .menu") == 0
    # Barcode's folder is read-only: no Change… on this card.
    assert _count(qtbot, view, f"{BAR} [data-act='folder']") == 0


def test_the_packing_list_menu_lists_every_list_and_a_choice_closes_it(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-list"))
    assert _attr(qtbot, view, _key("barcode-list"), "aria-expanded") == "true"
    assert _text(qtbot, view, f"{BAR} .menu-group") == "Packing lists in 2026-09-30_1"
    rows = _json(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('[data-act=\"list\"]')).map(i => "
        "[i.querySelector('.menu-label').textContent, i.querySelector('.menu-hint').textContent,"
        " i.getAttribute('aria-checked')])",
    )
    assert rows == [["DHL", "120", "true"], ["DPD", "48", "false"], ["Royal Mail", "31", "false"]]
    seen = _caught(bridge.listChosen)
    _click(qtbot, view, _key("barcode-list-item-2"))
    qtbot.waitUntil(lambda: seen == [("Royal Mail",)])
    assert _count(qtbot, view, f"{BAR} .menu") == 0
    assert _eval(qtbot, view, "document.activeElement.dataset.key") == "barcode-list"


def test_escape_and_an_outside_click_close_the_menu(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-list"))
    assert _count(qtbot, view, f"{BAR} .menu") == 1
    _eval(
        qtbot,
        view,
        "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); true",
    )
    assert _count(qtbot, view, f"{BAR} .menu") == 0
    assert _eval(qtbot, view, "document.activeElement.dataset.key") == "barcode-list"

    _click(qtbot, view, _key("barcode-list"))
    assert _count(qtbot, view, f"{BAR} .menu") == 1
    _click(qtbot, view, ".page-title")
    assert _count(qtbot, view, f"{BAR} .menu") == 0


def test_only_one_menu_is_open_at_a_time(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-list"))
    _click(qtbot, view, _key("reference-printer"))
    assert _count(qtbot, view, ".menu") == 1
    assert _count(qtbot, view, f"{REF} .menu") == 1


def test_arrow_keys_walk_the_open_menu(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-list"))
    down = "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowDown', bubbles: true})); document.activeElement.dataset.key"
    up = "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowUp', bubbles: true})); document.activeElement.dataset.key"
    assert _eval(qtbot, view, down) == "barcode-list-item-0"
    assert _eval(qtbot, view, down) == "barcode-list-item-1"
    assert _eval(qtbot, view, up) == "barcode-list-item-0"
    assert _eval(qtbot, view, up) == "barcode-list-item-2"


def test_a_state_push_leaves_an_open_menu_open(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-list"))
    _show(qtbot, view, bridge, make_state(reference=reference(open_pdf=False)))
    assert _count(qtbot, view, f"{BAR} .menu") == 1


def test_a_menu_closes_when_its_card_locks(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-list"))
    _show(
        qtbot,
        view,
        bridge,
        make_state(barcode=barcode(run=ToolRun("Writing 120 barcode labels…"))),
    )
    assert _count(qtbot, view, ".menu") == 0
    assert _disabled(qtbot, view, _key("barcode-list")) is True


def test_a_list_name_with_markup_is_drawn_as_text_and_sent_back_exactly(qtbot, page):
    view, bridge = page
    name = 'DHL "Express" <b>&co'
    lists = (PackingList(name, 3), PackingList("DPD", 48))
    _show(qtbot, view, bridge, make_state(barcode=barcode(lists=lists, selected=name)))
    assert _text(qtbot, view, f"{_key('barcode-list')} .select-value") == name
    assert _count(qtbot, view, f"{BAR} b") == 0
    _click(qtbot, view, _key("barcode-list"))
    seen = _caught(bridge.listChosen)
    _click(qtbot, view, _key("barcode-list-item-0"))
    qtbot.waitUntil(lambda: seen == [(name,)])


def test_with_no_lists_the_select_is_disabled_and_refresh_is_not(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(barcode=barcode(lists=(), selected="", folder="")))
    assert _disabled(qtbot, view, _key("barcode-list")) is True
    assert _text(qtbot, view, f"{_key('barcode-list')} .select-value") == "No packing lists"
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, f"{_key('barcode-list')} .select-value", "color") == _rgb(
        theme.text_disabled
    )
    seen = _caught(bridge.listsRequested)
    _click(qtbot, view, _key("barcode-refresh"))
    qtbot.waitUntil(lambda: seen == [()])


def test_the_barcode_checkboxes_report_their_option(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    seen = _caught(bridge.optionChanged)
    _click(qtbot, view, _key("barcode-qr"))
    _click(qtbot, view, _key("barcode-open_pdf"))
    qtbot.waitUntil(
        lambda: seen == [("barcode", "qr", True), ("barcode", "open_pdf", False)]
    )


def test_the_qr_print_button_appears_with_its_state(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _count(qtbot, view, _key("barcode-print-qr")) == 0
    _show(qtbot, view, bridge, make_state(barcode=barcode(qr=True)))
    assert _text(qtbot, view, _key("barcode-print-qr")) == "Print QR labels"
    assert _disabled(qtbot, view, _key("barcode-print-qr")) is True
    assert _attr(qtbot, view, _key("barcode-print-qr"), "title") == (
        "Generate with QR labels ticked first"
    )


# --- print mode ---------------------------------------------------------------


def test_the_mode_switch_shows_and_reports_the_mode(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _attr(qtbot, view, _key("reference-mode-driver"), "aria-checked") == "true"
    assert _attr(qtbot, view, _key("reference-mode-raw_zpl"), "aria-checked") == "false"
    assert _attr(qtbot, view, _key("barcode-mode-raw_zpl"), "aria-checked") == "true"
    seen = _caught(bridge.printChanged)
    _click(qtbot, view, _key("reference-mode-raw_zpl"))
    _click(qtbot, view, _key("barcode-mode-driver"))
    qtbot.waitUntil(
        lambda: seen == [("reference", "mode", "raw_zpl"), ("barcode", "mode", "driver")]
    )


def test_the_printer_menu_reports_a_printer_by_name(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _text(qtbot, view, f"{_key('reference-printer')} .select-value") == "Windows default"
    assert _text(qtbot, view, f"{_key('barcode-printer')} .select-value") == "Zebra ZD421"
    _click(qtbot, view, _key("reference-printer"))
    labels = _json(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('[data-act=\"printer\"] .menu-label')).map(e => e.textContent)",
    )
    assert labels == ["Windows default", "Zebra ZD421", "HP LaserJet"]
    seen = _caught(bridge.printChanged)
    _click(qtbot, view, _key("reference-printer-item-2"))
    qtbot.waitUntil(lambda: seen == [("reference", "printer", "HP LaserJet")])
    assert _count(qtbot, view, ".menu") == 0

    _click(qtbot, view, _key("reference-printer"))
    _click(qtbot, view, _key("reference-printer-item-0"))
    qtbot.waitUntil(lambda: seen[-1] == ("reference", "printer", ""))


def test_the_help_line_follows_the_mode_and_turns_danger_with_no_printer(qtbot, page):
    view, bridge = page
    theme = get_theme_manager().get_current_theme()
    _show(qtbot, view, bridge, make_state())
    assert _text(qtbot, view, f"{REF} .mode-help") == (
        "Prints stamped labels through the Windows print dialog. Saved for this PC."
    )
    assert _style(qtbot, view, f"{REF} .mode-help", "color") == _rgb(theme.text_secondary)
    no_target = PrintFacts({**ZPL, "raw_zpl_target": ""}, PRINTERS)
    _show(qtbot, view, bridge, make_state(barcode_print=no_target))
    assert _text(qtbot, view, f"{BAR} .mode-help") == (
        "Raw ZPL needs a printer. Choose the one the labels go to."
    )
    assert _style(qtbot, view, f"{BAR} .mode-help", "color") == _rgb(theme.status_danger)
    assert _text(qtbot, view, f"{_key('barcode-printer')} .select-value") == "Choose a printer"
    assert _style(qtbot, view, f"{_key('barcode-printer')} .select-value", "color") == _rgb(
        theme.text_placeholder
    )


def test_label_setup_shows_only_in_raw_zpl_and_folds(qtbot, page):
    view, bridge = page
    sized = PrintFacts(
        {**ZPL, "raw_zpl_label_width_mm": 68.0, "raw_zpl_label_height_mm": 38.0}, PRINTERS
    )
    _show(qtbot, view, bridge, make_state(barcode_print=sized))
    assert _count(qtbot, view, _key("reference-fold")) == 0  # Driver mode
    assert _text(qtbot, view, f"{_key('barcode-fold')} .fold-title") == "Label setup"
    assert _text(qtbot, view, f"{_key('barcode-fold')} .fold-summary") == "68 × 38 mm"
    assert _attr(qtbot, view, _key("barcode-fold"), "aria-expanded") == "false"
    assert _count(qtbot, view, ".fold-body") == 0

    _click(qtbot, view, _key("barcode-fold"))
    assert _attr(qtbot, view, _key("barcode-fold"), "aria-expanded") == "true"
    assert _eval(qtbot, view, f"document.querySelector({_key('barcode-target')!r}).value") == (
        "Zebra ZD421"
    )
    assert _eval(qtbot, view, f"document.querySelector({_key('barcode-width')!r}).value") == "68"
    assert _eval(qtbot, view, f"document.querySelector({_key('barcode-height')!r}).value") == "38"
    assert _attr(qtbot, view, _key("barcode-width"), "title").startswith("Physical label size")

    # A state push leaves it open.
    _show(qtbot, view, bridge, make_state(barcode_print=sized, reference=reference(csv=None)))
    assert _count(qtbot, view, ".fold-body") == 1

    _click(qtbot, view, _key("barcode-fold"))
    assert _count(qtbot, view, ".fold-body") == 0


def test_a_zero_label_size_shows_as_empty(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-fold"))
    assert _eval(qtbot, view, f"document.querySelector({_key('barcode-width')!r}).value") == ""
    assert _attr(qtbot, view, _key("barcode-width"), "placeholder") == "PDF"


def test_each_label_setup_control_reports_a_typed_value(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-fold"))
    seen = _caught(bridge.printChanged)

    _change(qtbot, view, _key("barcode-target"), r"\\printsrv\zebra-3")
    _change(qtbot, view, _key("barcode-width"), "68.5")
    _change(qtbot, view, _key("barcode-height"), "")
    _click(qtbot, view, _key("barcode-rotate"))
    _click(qtbot, view, _key("barcode-invert"))
    qtbot.waitUntil(lambda: len(seen) == 5)

    assert seen[0] == ("barcode", "target", r"\\printsrv\zebra-3")
    assert seen[1] == ("barcode", "width", 68.5)
    assert seen[2] == ("barcode", "height", 0)
    assert seen[3] == ("barcode", "rotate", True)
    assert seen[4] == ("barcode", "invert", True)
    # The types apply_print_edit checks: a number is never a bool, a bool never a number.
    assert isinstance(seen[0][2], str)
    assert not isinstance(seen[1][2], bool) and isinstance(seen[1][2], (int, float))
    assert not isinstance(seen[2][2], bool) and isinstance(seen[2][2], (int, float))
    assert seen[3][2] is True and seen[4][2] is True


def test_text_being_typed_survives_a_state_that_arrives_mid_edit(qtbot, page):
    """The other card's run pushes a state several times a second."""
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-fold"))
    _eval(
        qtbot,
        view,
        f"(function () {{ const el = document.querySelector({_key('barcode-target')!r});"
        " el.focus(); el.value = 'Zebra ZD4'; return true; })()",
    )
    _show(qtbot, view, bridge, make_state(reference=reference(run=ToolRun(STAMPING, 1, 120))))
    assert _eval(qtbot, view, "document.activeElement.dataset.key") == "barcode-target"
    assert _eval(qtbot, view, "document.activeElement.value") == "Zebra ZD4"


# --- footer -------------------------------------------------------------------


def test_the_idle_footers_state_the_reason_and_offer_the_actions(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _text(qtbot, view, f"{REF} .tool-reason") == "120 pages, 120 CSV rows."
    assert _text(qtbot, view, _key("reference-run")) == "Process labels"
    assert _text(qtbot, view, _key("barcode-run")) == "Generate barcode labels"
    assert _disabled(qtbot, view, _key("reference-run")) is False
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, _key("reference-run"), "backgroundColor") == _rgb(
        theme.accent_fill
    )
    assert _style(qtbot, view, _key("barcode-run"), "backgroundColor") == _rgb(
        theme.accent_fill
    )
    seen = _caught(bridge.runRequested)
    _click(qtbot, view, _key("reference-run"))
    _click(qtbot, view, _key("barcode-run"))
    qtbot.waitUntil(lambda: seen == [("reference",), ("barcode",)])


def test_a_disabled_primary_reports_nothing(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(reference=reference(pdf=None)))
    assert _disabled(qtbot, view, _key("reference-run")) is True
    seen = _caught(bridge.runRequested)
    _click(qtbot, view, _key("reference-run"))
    _click(qtbot, view, _key("barcode-run"))
    qtbot.waitUntil(lambda: seen == [("barcode",)])


def test_the_warning_tone_colours_the_reason(qtbot, page):
    view, bridge = page
    result = {"list": "DHL", "labels": 118, "failed": 2}
    _show(qtbot, view, bridge, make_state(barcode=barcode(result=result)))
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, f"{BAR} .tool-reason", "color") == _rgb(theme.status_warning)


def test_the_print_buttons_follow_their_state(qtbot, page):
    view, bridge = page
    lists = (PackingList("DHL", 120, has_labels=True, has_qr=True),)
    _show(
        qtbot,
        view,
        bridge,
        make_state(reference=reference(has_output=True), barcode=barcode(lists=lists)),
    )
    assert _text(qtbot, view, _key("reference-print-labels")) == "Print…"
    assert _attr(qtbot, view, _key("reference-print-labels"), "title") == "Open the print dialog"
    assert _text(qtbot, view, _key("barcode-print-labels")) == "Print"
    assert _attr(qtbot, view, _key("barcode-print-labels"), "title") == "Send to Zebra ZD421"
    seen = _caught(bridge.printRequested)
    _click(qtbot, view, _key("reference-print-labels"))
    _click(qtbot, view, _key("barcode-print-qr"))
    _click(qtbot, view, _key("barcode-print-labels"))
    qtbot.waitUntil(
        lambda: seen == [("reference", "labels"), ("barcode", "qr"), ("barcode", "labels")]
    )


def test_print_before_a_run_is_disabled_and_says_why(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _disabled(qtbot, view, _key("reference-print-labels")) is True
    assert _attr(qtbot, view, _key("reference-print-labels"), "title") == "Process labels first"
    assert _disabled(qtbot, view, _key("barcode-print-labels")) is True


def test_a_counted_run_shows_its_count_its_bar_and_cancel(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(reference=reference(run=ToolRun(STAMPING, 40, 120))))
    assert _text(qtbot, view, f"{REF} .run-label") == "Stamping labels — 40 of 120"
    assert _text(qtbot, view, f"{REF} .run-count") == "40 of 120"
    track = _eval(qtbot, view, "document.querySelector('.run-track').getBoundingClientRect().width")
    fill = _eval(qtbot, view, "document.querySelector('.run-fill').getBoundingClientRect().width")
    assert abs(fill / track - 0.66) < 0.02
    assert _count(qtbot, view, _key("reference-run")) == 0
    assert _count(qtbot, view, _key("reference-print-labels")) == 0
    assert _text(qtbot, view, _key("reference-cancel")) == "Cancel"
    seen = _caught(bridge.cancelRequested)
    _click(qtbot, view, _key("reference-cancel"))
    qtbot.waitUntil(lambda: seen == [()])


def test_cancel_is_disabled_while_cancelling_and_while_saving(qtbot, page):
    view, bridge = page
    _show(
        qtbot,
        view,
        bridge,
        make_state(reference=reference(run=ToolRun(STAMPING, 40, 120, cancelling=True))),
    )
    assert _text(qtbot, view, _key("reference-cancel")) == "Cancelling…"
    assert _disabled(qtbot, view, _key("reference-cancel")) is True
    _show(qtbot, view, bridge, make_state(reference=reference(run=ToolRun(SAVING, 120, 120))))
    assert _text(qtbot, view, f"{REF} .run-label") == "Saving…"
    assert _disabled(qtbot, view, _key("reference-cancel")) is True
    assert _attr(qtbot, view, _key("reference-cancel"), "title") == "Saving can't be cancelled"


def test_a_barcode_run_is_one_sentence_with_no_bar_and_no_cancel(qtbot, page):
    view, bridge = page
    _show(
        qtbot,
        view,
        bridge,
        make_state(barcode=barcode(run=ToolRun("Writing 120 barcode labels…"))),
    )
    assert _text(qtbot, view, f"{BAR} .run-label") == "Writing 120 barcode labels…"
    assert _count(qtbot, view, f"{BAR} .run-track") == 0
    assert _count(qtbot, view, f"{BAR} [data-act='cancel']") == 0
    assert _count(qtbot, view, _key("barcode-run")) == 0


def test_a_running_card_locks_its_inputs_and_leaves_the_other_card_alone(qtbot, page):
    view, bridge = page
    zpl = PrintFacts(ZPL, PRINTERS)
    _show(
        qtbot,
        view,
        bridge,
        make_state(
            reference=reference(run=ToolRun(STAMPING, 40, 120)), reference_print=zpl
        ),
    )
    _click(qtbot, view, _key("reference-fold"))
    for key in (
        "pdf-clear",
        "csv-clear",
        "reference-folder",
        "reference-open_pdf",
        "reference-mode-driver",
        "reference-mode-raw_zpl",
        "reference-printer",
        "reference-target",
        "reference-width",
        "reference-rotate",
    ):
        assert _disabled(qtbot, view, _key(key)) is True, key
    assert _disabled(qtbot, view, _key("reference-fold")) is False
    for key in ("barcode-list", "barcode-refresh", "barcode-qr", "barcode-mode-driver", "barcode-run"):
        assert _disabled(qtbot, view, _key(key)) is False, key


# --- toast and drops ----------------------------------------------------------


def test_the_done_toast_offers_open_folder(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    bridge.raise_toast("120 barcode labels saved to …/barcodes/DHL", True)
    _until_js(qtbot, view, "document.getElementById('toast').hidden === false")
    assert _text(qtbot, view, "#toast-text") == "120 barcode labels saved to …/barcodes/DHL"
    assert _eval(qtbot, view, "document.getElementById('toast-action').hidden") is False
    assert _text(qtbot, view, "#toast-action") == "Open folder"
    seen = _caught(bridge.folderOpenRequested)
    _click(qtbot, view, "#toast-action")
    qtbot.waitUntil(lambda: seen == [()])
    assert _eval(qtbot, view, "document.getElementById('toast').hidden") is True


def test_a_plain_toast_has_no_action_and_can_be_dismissed(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    bridge.raise_toast("Processing cancelled", False)
    _until_js(qtbot, view, "document.getElementById('toast').hidden === false")
    assert _eval(qtbot, view, "document.getElementById('toast-action').hidden") is True
    _click(qtbot, view, "#toast-dismiss")
    assert _eval(qtbot, view, "document.getElementById('toast').hidden") is True


def test_a_file_dropped_on_the_page_does_not_navigate_it(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    for name in ("dragover", "drop"):
        prevented = _eval(
            qtbot,
            view,
            f"(function () {{ const e = new Event({name!r}, {{bubbles: true, cancelable: true}});"
            " document.body.dispatchEvent(e); return e.defaultPrevented; })()",
        )
        assert prevented is True


def test_driver_mode_for_both_tools_draws_no_fold(qtbot, page):
    view, bridge = page
    driver = PrintFacts(DRIVER, PRINTERS)
    _show(qtbot, view, bridge, make_state(reference_print=driver, barcode_print=driver))
    assert _count(qtbot, view, ".fold") == 0
    assert _text(qtbot, view, _key("barcode-print-labels")) == "Print…"


def test_left_and_right_move_between_the_two_mode_segments(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())

    def press(start, key):
        return _eval(
            qtbot,
            view,
            f"(function () {{ const el = document.querySelector({_key(start)!r}); el.focus();"
            f" el.dispatchEvent(new KeyboardEvent('keydown', {{key: {key!r}, bubbles: true}}));"
            " return document.activeElement.dataset.key; })()",
        )

    assert press("reference-mode-driver", "ArrowRight") == "reference-mode-raw_zpl"
    assert press("reference-mode-raw_zpl", "ArrowRight") == "reference-mode-driver"  # wraps
    assert press("barcode-mode-raw_zpl", "ArrowLeft") == "barcode-mode-driver"
    # Moving focus chooses nothing: Space or Enter does.
    assert _attr(qtbot, view, _key("reference-mode-driver"), "aria-checked") == "true"
