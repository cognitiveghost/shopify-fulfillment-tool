"""Settings knows which pages have unsaved changes, and closing never drops
them silently. Fixtures (window, started_workers, no_modals) come from
conftest.py."""

from PySide6.QtWidgets import QFileDialog

from gui.settings.window import unsaved_summary


def _nav_item(win, name):
    nav = win._settings_nav
    return next(
        nav.item(r)
        for r in range(nav.count())
        if nav.item(r).text() == name and nav.item(r).data(0x0100) is not None
    )


def _edit_sets(win):
    """Add a set the way the page does; its uid, to undo it with."""
    win._select_page("Sets")
    bridge = win._web_host.bridge
    bridge.edit("set_add", [])
    uid = bridge.state["sets"]["rows"][0]["uid"]
    bridge.edit("set_sku", [uid, "SET-NEW"])
    bridge.edit("comp_sku", [uid, "0", "A"])
    return uid


def test_unsaved_summary_names_every_page():
    assert unsaved_summary([]) == ""
    assert unsaved_summary(["Sets"]) == "Unsaved changes in Sets"
    assert unsaved_summary(["General", "Sets", "Reports"]) == (
        "Unsaved changes in General, Sets, Reports"
    )


def test_a_fresh_window_has_no_unsaved_pages(window):
    assert window.refresh_dirty() == []
    assert window._status_label.text() == ""


def test_an_edit_marks_its_nav_row_and_the_footer(window):
    _edit_sets(window)
    assert window.refresh_dirty() == ["Sets"]
    assert _nav_item(window, "Sets").toolTip() == "Unsaved changes"
    assert _nav_item(window, "General").toolTip() == ""
    assert window._status_label.text() == "Unsaved changes in Sets"


def test_reverting_an_edit_clears_the_mark(window):
    uid = _edit_sets(window)
    window.refresh_dirty()
    window._web_host.bridge.edit("set_delete", [uid])
    assert window.refresh_dirty() == []
    assert _nav_item(window, "Sets").toolTip() == ""


def test_an_edit_is_marked_at_once_with_no_poll(window):
    assert not hasattr(window, "_dirty_poll")
    _edit_sets(window)
    assert window._status_label.text() == "Unsaved changes in Sets"
    window._select_page("General")
    assert _nav_item(window, "Sets").toolTip() == "Unsaved changes"


def test_cancel_with_nothing_unsaved_closes(window):
    closed = []
    window.rejected.connect(lambda: closed.append(True))
    window.reject()
    assert closed == [True]


def test_cancel_with_unsaved_pages_shows_the_close_guard_instead(window):
    closed = []
    window.rejected.connect(lambda: closed.append(True))
    _edit_sets(window)
    window.reject()
    assert closed == []
    assert not window._close_guard.isHidden()
    assert window._footer.isHidden()
    assert window._close_guard_label.text() == (
        "Unsaved changes in Sets. Closing now discards them."
    )
    assert window.save_and_close_button.text() == "Save && close"


def test_keep_editing_and_escape_both_restore_the_footer(window):
    _edit_sets(window)
    window.reject()
    window.keep_editing_button.click()
    assert window._close_guard.isHidden()
    assert not window._footer.isHidden()

    window.reject()
    window.reject()  # Esc while the guard is up keeps editing
    assert window._close_guard.isHidden()


def test_cancel_then_discard_leaves_the_profile_unwritten(
    window, started_workers, monkeypatch, tmp_path
):
    """9.23 done-when: import sets, Cancel, Discard -> nothing written."""
    path = tmp_path / "sets.csv"
    path.write_text("Set_SKU,Component_SKU,Component_Quantity\nSET-X,A,2\n", encoding="utf-8")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), ""))
    )
    closed = []
    window.rejected.connect(lambda: closed.append(True))

    window._select_page("Sets")
    window._web_host.bridge.importFile("sets-replace")
    assert window._status_label.text() == "Unsaved changes in Sets"
    window.reject()
    window.discard_button.click()

    assert closed == [True]
    assert started_workers == []
    window.profile_manager.save_shopify_config.assert_not_called()


def test_save_and_close_saves(window, started_workers):
    _edit_sets(window)
    window.reject()
    window.save_and_close_button.click()
    assert len(started_workers) == 1
    assert window._close_guard.isHidden()
