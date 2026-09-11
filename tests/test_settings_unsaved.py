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
    win._pages_by_name["Sets"].set_decoders["SET-NEW"] = [{"sku": "A", "quantity": 1}]


def test_unsaved_summary_names_up_to_two_pages():
    assert unsaved_summary([]) == ""
    assert unsaved_summary(["Sets"]) == "Unsaved changes on Sets"
    assert unsaved_summary(["Sets", "Reports"]) == "Unsaved changes on Sets and Reports"
    assert (
        unsaved_summary(["General", "Sets", "Reports"]) == "Unsaved changes on 3 pages"
    )


def test_a_fresh_window_has_no_unsaved_pages(window):
    assert window.refresh_dirty() == []
    assert window._unsaved_label.text() == ""


def test_an_edit_marks_its_nav_row_and_the_footer(window):
    _edit_sets(window)
    assert window.refresh_dirty() == ["Sets"]
    assert _nav_item(window, "Sets").toolTip() == "Unsaved changes"
    assert _nav_item(window, "General").toolTip() == ""
    assert window._unsaved_label.text() == "Unsaved changes on Sets"


def test_reverting_an_edit_clears_the_mark(window):
    _edit_sets(window)
    window.refresh_dirty()
    del window._pages_by_name["Sets"].set_decoders["SET-NEW"]
    assert window.refresh_dirty() == []
    assert _nav_item(window, "Sets").toolTip() == ""


def test_the_poll_checks_the_page_on_screen(window):
    assert window._dirty_poll.isActive()
    window._select_page("Sets")
    _edit_sets(window)
    window._poll_current_page()
    assert window._unsaved_label.text() == "Unsaved changes on Sets"


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
        "Unsaved changes on Sets. Closing now discards them."
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
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / "sets.csv"), "")),
    )
    monkeypatch.setattr(
        "gui.settings.sets.import_sets_from_csv",
        lambda path: {"SET-X": [{"sku": "A", "quantity": 2}]},
    )
    monkeypatch.setattr("gui.settings.sets.toast", lambda *a, **k: None)
    closed = []
    window.rejected.connect(lambda: closed.append(True))

    window._pages_by_name["Sets"]._import_sets_from_csv(replace=True)
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


def test_closing_stops_the_poll(window):
    window.done(0)
    assert not window._dirty_poll.isActive()
