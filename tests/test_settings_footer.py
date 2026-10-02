"""The settings footer, Save and closing (phase 7 spec sections 6.3 and 6.4).

Fixtures (window, started_workers, no_modals, make_settings_config) come from
conftest.py. A web page is edited through the host's bridge, as the page does.
"""

from unittest.mock import Mock

from PySide6.QtWidgets import QDialog

from gui.settings.window import SAVED_LINE, SettingsWindow


def _edit_sets(win):
    win._pages_by_name["Sets"].set_decoders["SET-NEW"] = [{"sku": "A", "quantity": 1}]


def _edit_general(win, text="9"):
    win._select_page("General")
    win._web_host.bridge.edit("threshold", [text])


def _results(win):
    seen = []
    win.finished.connect(seen.append)
    return seen


# --- the status line ---------------------------------------------------------


def test_a_fresh_window_says_nothing_and_cannot_save(window):
    assert window._status_label.text() == ""
    assert window._status_icon.isHidden()
    assert not window.save_button.isEnabled()
    assert window.cancel_button.text() == "Cancel"
    assert window.save_button.toolTip() == "Ctrl+S"


def test_an_unsaved_page_is_named_and_makes_save_live(window):
    _edit_general(window)
    assert window._status_label.text() == "Unsaved changes in General"
    assert not window._status_icon.isHidden()
    assert window.save_button.isEnabled()


def test_every_unsaved_page_is_named_in_nav_order(window):
    _edit_sets(window)
    _edit_general(window)
    window.refresh_dirty()
    assert window._status_label.text() == "Unsaved changes in General, Sets"


def test_undoing_the_edit_empties_the_line_and_disables_save(window):
    _edit_general(window)
    _edit_general(window, "5")
    assert window._status_label.text() == ""
    assert not window.save_button.isEnabled()


def test_a_blocker_takes_the_line_and_disables_save(window):
    _edit_general(window, "x")
    text = window._status_label.text()
    assert text.startswith('Set Low-stock threshold in <a href="General"')
    assert text.endswith(">General</a> to save.")
    assert not window.save_button.isEnabled()
    assert not window.save_and_close_button.isEnabled()

    _edit_general(window, "7")
    assert window._status_label.text() == "Unsaved changes in General"
    assert window.save_button.isEnabled()
    assert window.save_and_close_button.isEnabled()


def test_the_first_blocked_page_in_nav_order_is_the_one_named(
    qapp, no_modals, started_workers, make_settings_config
):
    config = make_settings_config()
    del config["column_mappings"]["orders"]["Shipping Method"]
    win = SettingsWindow(client_id="M", client_config=config, profile_manager=Mock())
    assert "Map Shipping method in" in win._status_label.text()
    assert ">Orders mapping</a>" in win._status_label.text()
    _edit_general(win, "x")
    assert ">General</a>" in win._status_label.text()
    win.deleteLater()


def test_the_lines_link_opens_the_page_and_points_at_the_control(window):
    window._web_host.drafts["general"].apply("threshold", ["x"])
    window._refresh_status()
    window._select_page("Sets")
    asked = []
    window._web_host.bridge.problemFocusRequested.connect(asked.append)

    window._status_label.linkActivated.emit("General")

    assert window._settings_nav.currentItem().text() == "General"
    assert asked == ["threshold"]


def test_a_link_to_no_page_does_nothing(window):
    window._status_label.linkActivated.emit("Nope")
    assert window._settings_nav.currentItem().text() == "General"


def test_a_disabled_save_and_close_says_what_blocks_it(window):
    """The close guard hides the status line that would have said it."""
    _edit_general(window, "x")
    assert (
        window.save_and_close_button.toolTip()
        == "Set Low-stock threshold in General to save."
    )
    _edit_general(window, "7")
    assert window.save_and_close_button.toolTip() == ""


def test_the_loaded_file_is_split_on_the_clients_saved_delimiter(
    qapp, no_modals, started_workers, make_settings_config, tmp_path
):
    """Setup read it with the client's override, so the mapping page must:
    detection alone would split this one on its commas."""
    path = tmp_path / "orders.csv"
    path.write_text("Name|Note, a, b\n#1|x, y, z\n", encoding="utf-8")
    config = make_settings_config()
    config["settings"]["orders_csv_delimiter"] = "|"
    win = SettingsWindow(
        client_id="M",
        client_config=config,
        profile_manager=Mock(),
        loaded_files={"orders": str(path)},
    )
    assert win._web_host.drafts["orders"].file.columns == ("Name", "Note, a, b")
    win.deleteLater()


# --- Save --------------------------------------------------------------------


def test_save_writes_a_copy_and_the_dialog_stays_open(window, started_workers):
    results = _results(window)
    _edit_general(window)

    window.save_button.click()

    assert len(started_workers) == 1
    assert window.save_button.text() == "Saving…"
    assert not window.save_button.isEnabled()
    written = started_workers[0].args[1]
    assert written == window.config_data
    assert written is not window.config_data
    assert written["settings"]["low_stock_threshold"] == 9

    window._on_save_settings_result(True)

    assert results == []
    assert window._status_label.text() == SAVED_LINE
    assert window.save_button.text() == "Save"
    assert not window.save_button.isEnabled()
    assert window.cancel_button.text() == "Close"
    assert window.refresh_dirty() == []
    assert window._settings_nav.currentItem().toolTip() == ""


def test_an_edit_after_a_save_brings_the_unsaved_line_and_cancel_back(window):
    _edit_general(window)
    window.save_settings()
    window._on_save_settings_result(True)

    _edit_general(window, "11")

    assert window._status_label.text() == "Unsaved changes in General"
    assert window.cancel_button.text() == "Cancel"
    assert window.save_button.isEnabled()
    # Undoing it does not bring "Saved" back: that line is the save's own.
    _edit_general(window, "9")
    assert window._status_label.text() == ""


def test_an_edit_made_while_the_write_runs_stays_unsaved(window, started_workers):
    _edit_general(window)
    window.save_settings()
    _edit_general(window, "12")

    window._on_save_settings_result(True)

    assert started_workers[0].args[1]["settings"]["low_stock_threshold"] == 9
    assert window.refresh_dirty() == ["General"]
    assert window._status_label.text() == "Unsaved changes in General"
    assert window.save_button.isEnabled()


def test_a_failed_write_leaves_the_page_unsaved_and_save_live(window, monkeypatch):
    monkeypatch.setattr("gui.settings.window.show_error", lambda *a: None)
    _edit_general(window)
    window.save_settings()

    window._on_save_settings_result(False)

    assert window._status_label.text() == "Unsaved changes in General"
    assert window.save_button.isEnabled()
    assert window.save_button.text() == "Save"


def test_a_crashed_write_leaves_save_live(window, monkeypatch):
    monkeypatch.setattr("gui.settings.window.show_error", lambda *a: None)
    _edit_general(window)
    window.save_settings()
    window._on_save_settings_error((ValueError, ValueError("disk"), "tb"))
    assert window.save_button.isEnabled()
    assert window.save_button.text() == "Save"


def test_ctrl_s_saves_an_edit_the_poll_has_not_seen(window, started_workers):
    _edit_sets(window)
    assert not window.save_button.isEnabled()
    window._save_shortcut()
    assert len(started_workers) == 1


def test_ctrl_s_does_nothing_with_nothing_to_save_or_a_blocker(window, started_workers):
    window._save_shortcut()
    _edit_general(window, "x")
    window._save_shortcut()
    assert started_workers == []


# --- closing -----------------------------------------------------------------


def test_closing_without_a_save_is_rejected(window):
    results = _results(window)
    window.reject()
    assert results == [QDialog.DialogCode.Rejected]


def test_closing_after_a_save_is_accepted(window):
    results = _results(window)
    _edit_general(window)
    window.save_settings()
    window._on_save_settings_result(True)

    window.reject()

    assert results == [QDialog.DialogCode.Accepted]


def test_discarding_later_edits_after_a_save_is_still_accepted(window):
    """The main window reloads the profile on Accepted: one save is enough."""
    results = _results(window)
    _edit_general(window)
    window.save_settings()
    window._on_save_settings_result(True)
    _edit_general(window, "12")

    window.reject()
    assert results == []
    window.discard_button.click()

    assert results == [QDialog.DialogCode.Accepted]


def test_save_and_close_closes_once_the_write_succeeds(window, started_workers):
    results = _results(window)
    _edit_sets(window)
    window.reject()
    window.save_and_close_button.click()
    assert len(started_workers) == 1
    assert results == []

    window._on_save_settings_result(True)

    assert results == [QDialog.DialogCode.Accepted]


def test_save_and_close_asks_again_about_an_edit_made_while_the_write_ran(
    window, started_workers
):
    """That edit was not in the write: closing now would drop it unasked."""
    results = _results(window)
    _edit_sets(window)
    window.reject()
    window.save_and_close_button.click()
    _edit_general(window, "12")

    window._on_save_settings_result(True)

    assert results == []
    assert not window._close_guard.isHidden()
    assert window._close_guard_label.text() == (
        "Unsaved changes in General. Closing now discards them."
    )
    # A second Save & close writes it and closes.
    window.save_and_close_button.click()
    window._on_save_settings_result(True)
    assert started_workers[1].args[1]["settings"]["low_stock_threshold"] == 12
    assert results == [QDialog.DialogCode.Accepted]


def test_save_and_close_stays_open_when_the_write_fails(window, monkeypatch):
    monkeypatch.setattr("gui.settings.window.show_error", lambda *a: None)
    results = _results(window)
    _edit_sets(window)
    window.reject()
    window.save_and_close_button.click()
    window._on_save_settings_result(False)
    assert results == []

    # A plain Save afterwards does not inherit the close.
    window.save_settings()
    window._on_save_settings_result(True)
    assert results == []


def test_nothing_closes_the_dialog_while_a_write_runs(window):
    results = _results(window)
    _edit_general(window)
    window.save_settings()
    window.reject()
    assert results == []
