"""Setup is one web page in tab 0 (phase 3 spec sections 3 and 4.5).

What the page draws is tested in test_setup_page.py and what the state says
in test_setup_state.py. This file tests the wiring: the window builds the
state from its own facts and the page's requests reach the handlers.
"""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from gui.setup_bridge import SetupView
from gui.setup_state import FileSlot


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1366, 768)
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


@pytest.fixture
def client_window(main_window):
    """The window with one client loaded, as test_file_handler.py does it."""
    main_window.profile_manager.create_client_profile("acme", "Client Acme")
    main_window.current_client_id = "acme"
    main_window.current_client_config = main_window.profile_manager.load_shopify_config(
        "acme"
    )
    main_window.load_client_config("acme")
    main_window.update_ui_state()
    return main_window


def _state(win):
    return win.setup_bridge.state


def _write_inputs(tmp_path):
    orders = tmp_path / "orders.csv"
    orders.write_text(
        "Name,Lineitem sku,Lineitem quantity,Shipping Method\n"
        "#1,A1,2,Standard\n#1,B2,1,Standard\n#2,A1,1,Express\n",
        encoding="utf-8",
    )
    stock = tmp_path / "stock.csv"
    stock.write_text("Артикул;Наличност\nA1;5\nB2;3\n", encoding="utf-8")
    return orders, stock


def test_tab_0_holds_the_setup_view(main_window):
    assert isinstance(main_window.setup_view, SetupView)
    assert main_window.main_tabs.widget(0).findChild(SetupView) is main_window.setup_view


def test_the_qt_setup_card_is_gone(main_window):
    for name in (
        "setup_stack",
        "setup_state_panel",
        "inventory_memory_checkbox",
        "strategy_multi_item",
        "strategy_fifo",
    ):
        assert not hasattr(main_window, name), name


def test_the_slots_are_records(main_window):
    assert isinstance(main_window.orders_slot, FileSlot)
    assert isinstance(main_window.stock_slot, FileSlot)
    assert main_window.orders_slot.kind == "orders"
    assert main_window.stock_slot.kind == "stock"


def test_with_no_client_the_page_asks_for_one(main_window):
    assert _state(main_window)["view"] == "no_client"


def test_a_client_with_no_session_gets_the_no_session_view(client_window):
    state = _state(client_window)
    assert state["view"] == "no_session"
    assert state["client"] == "acme"
    assert client_window.run_analysis_button.isEnabled() is False


def test_new_session_opens_the_cards(client_window):
    client_window.setup_bridge.newSession()
    state = _state(client_window)
    assert state["view"] == "setup"
    assert state["session"]["name"] == Path(client_window.session_path).name
    assert state["session"]["title"] == "New session"
    assert state["session"]["meta"].startswith("acme · opened ")
    assert state["files"]["orders"]["state"] == "missing"


def test_run_follows_the_one_rule(client_window, tmp_path):
    orders, stock = _write_inputs(tmp_path)
    client_window.setup_bridge.newSession()

    client_window.file_handler.load_file("orders", str(orders))
    assert _state(client_window)["files"]["orders"]["state"] == "loaded"
    assert client_window.run_analysis_button.isEnabled() is False

    client_window.file_handler.load_file("stock", str(stock))
    state = _state(client_window)
    assert state["run"]["enabled"] is True
    assert client_window.run_analysis_button.isEnabled() is True
    assert state["summary"]["headline"] == (
        "2 orders, 3 lines, stock for 2 SKUs, multi-item first"
    )
    assert [s["v"] for s in state["files"]["stock"]["stats"]] == ["2", "2", "Semicolon  ;"]


def test_replace_empties_the_card(client_window, tmp_path):
    orders, _stock = _write_inputs(tmp_path)
    client_window.setup_bridge.newSession()
    client_window.file_handler.load_file("orders", str(orders))

    client_window.setup_bridge.clearFile("orders")

    assert client_window.orders_file_path is None
    assert _state(client_window)["files"]["orders"]["state"] == "missing"


def test_losing_the_server_keeps_the_cards_and_stops_run(client_window, tmp_path):
    orders, stock = _write_inputs(tmp_path)
    client_window.setup_bridge.newSession()
    client_window.file_handler.load_file("orders", str(orders))
    client_window.file_handler.load_file("stock", str(stock))

    client_window.profile_manager.is_network_available = False
    client_window.connectionChanged.emit(False)

    state = _state(client_window)
    assert state["view"] == "setup"
    assert state["run"]["enabled"] is False
    assert state["summary"]["reason_tone"] == "danger"
    assert client_window.run_analysis_button.isEnabled() is False


def test_the_page_buttons_reach_the_file_dialogs(client_window, monkeypatch):
    calls = []
    handler = client_window.file_handler
    monkeypatch.setattr(handler, "select_orders_file", lambda: calls.append("orders file"))
    monkeypatch.setattr(handler, "select_stock_file", lambda: calls.append("stock file"))
    monkeypatch.setattr(handler, "select_folder", lambda kind: calls.append(f"{kind} folder"))

    bridge = client_window.setup_bridge
    bridge.chooseFile("orders")
    bridge.chooseFile("stock")
    bridge.chooseFolder("orders")

    assert calls == ["orders file", "stock file", "orders folder"]


def test_a_dropped_path_takes_the_file_route(client_window, monkeypatch):
    seen = []
    monkeypatch.setattr(
        client_window.file_handler, "load_file", lambda kind, path: seen.append((kind, path))
    )
    client_window.setup_view.pathDropped.emit("stock", "/d/s.csv")
    assert seen == [("stock", "/d/s.csv")]


def test_the_strategy_is_saved_to_the_client(client_window):
    client_window.setup_bridge.setStrategy("fifo")
    assert client_window.active_profile_config["analysis_mode"] == "fifo"
    assert _state(client_window)["strategy"] == "fifo"
    saved = client_window.profile_manager.load_shopify_config("acme")
    assert saved["analysis_mode"] == "fifo"


def test_the_memory_switch_is_saved_to_the_client(client_window):
    client_window.setup_bridge.setMemory(False)
    assert client_window.active_profile_config["inventory_memory"]["enabled"] is False
    assert _state(client_window)["memory"]["on"] is False
    client_window.setup_bridge.setMemory(True)
    assert _state(client_window)["memory"]["on"] is True


def test_the_fix_link_opens_the_page_the_problem_names(client_window, monkeypatch):
    opened = []
    monkeypatch.setattr(
        client_window.actions_handler,
        "open_settings_window",
        lambda page=None: opened.append(page),
    )
    client_window.orders_slot.set_invalid(
        "/d/o.csv", ["Lineitem sku"], ["Name"], {"Lineitem sku": "SKU"}
    )

    client_window.setup_bridge.fixProblem("orders")
    client_window.setup_bridge.fixProblem("stock")  # no problem there: nothing opens

    assert opened == ["Orders Mapping"]


def test_open_recent_from_the_page_opens_the_bars_menu(client_window, monkeypatch):
    shown = []
    monkeypatch.setattr(
        client_window.command_bar.session_button, "showMenu", lambda: shown.append(1)
    )
    client_window.setup_bridge.openRecent()
    assert shown == [1]


def test_the_unreachable_button_opens_the_connection_dialog(client_window, monkeypatch):
    opened = []
    monkeypatch.setattr(
        client_window.ui_manager, "_open_connection_settings", lambda: opened.append(1)
    )
    client_window.setup_bridge.openConnection()
    assert opened == [1]


def test_run_from_the_page_clicks_the_hidden_run_button(client_window, monkeypatch):
    """The hidden button is the guard: the page goes through it, never round it."""
    clicks = []
    monkeypatch.setattr(
        client_window.run_analysis_button, "click", lambda: clicks.append(1)
    )
    client_window.setup_bridge.runAnalysis()
    assert clicks == [1]


def test_an_opened_session_brings_its_facts(client_window, tmp_path):
    path = client_window.session_manager.create_session("acme")
    client_window.load_existing_session(path)
    state = _state(client_window)
    assert state["view"] == "setup"
    assert state["session"]["name"] == Path(path).name


def test_cancel_from_the_page_reaches_the_run(client_window, monkeypatch):
    cancelled = []
    monkeypatch.setattr(
        client_window.actions_handler, "cancel_analysis", lambda: cancelled.append(1)
    )
    client_window.setup_bridge.cancelRun()
    assert cancelled == [1]


def test_a_step_shows_on_the_page_and_in_the_bar(client_window):
    client_window.setup_bridge.newSession()
    client_window._analysis_running = True
    client_window.actions_handler.analysis_progress.emit(2)

    run = client_window.setup_bridge.state["run"]
    assert (run["running"], run["step"], run["step_name"]) == (
        True,
        2,
        "Allocating stock",
    )
    assert client_window.command_bar.step_count_label.text() == "Step 3 of 4"
    assert client_window.run_analysis_button.isEnabled() is False

    client_window.actions_handler.cancel_analysis()
    run = client_window.setup_bridge.state["run"]
    assert (run["cancelling"], run["can_cancel"]) == (True, False)

    client_window.actions_handler._on_analysis_finished()
    assert client_window.setup_bridge.state["run"]["running"] is False
