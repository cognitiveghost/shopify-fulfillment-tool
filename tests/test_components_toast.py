"""9.25: good news never blocks.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §4.1
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QVBoxLayout, QWidget

from gui.components.toast import Toast, toast
from shared.theme import current_tokens


@pytest.fixture
def window(qapp):
    win = QMainWindow()
    win.setCentralWidget(QWidget())
    win.resize(800, 600)
    yield win
    win.close()


def test_the_toast_lives_on_the_window_that_raised_it(window):
    shown = toast(window.centralWidget(), "Session S1 created.")
    assert shown.parent() is window
    assert Toast.for_window(window) is shown
    assert not shown.isHidden()


def test_a_dialog_hosts_its_own_toast(window):
    dialog = QDialog(window)
    QVBoxLayout(dialog)
    shown = toast(dialog, "Group North created.")
    assert shown.parent() is dialog
    assert Toast.for_window(window) is None


def test_one_toast_per_window_and_the_newest_text_wins(window):
    first = toast(window, "One.")
    second = toast(window, "Two.")
    assert first is second
    assert second.text() == "Two."
    assert second.count() == 2


def test_the_badge_appears_at_three(window):
    for n in range(Toast.BADGE_AT - 1):
        shown = toast(window, f"Message {n}.")
    assert shown.badge.isHidden()
    shown = toast(window, "One more.")
    assert not shown.badge.isHidden()
    assert shown.badge.text() == str(Toast.BADGE_AT)


def test_the_timer_runs_for_the_stated_duration(window):
    shown = toast(window, "One.")
    assert shown.timer.isActive()
    assert shown.timer.interval() == Toast.DURATION_MS


def test_the_timer_hides_it_and_resets_the_count(window):
    shown = toast(window, "One.")
    toast(window, "Two.")
    shown.timer.timeout.emit()
    assert shown.isHidden()
    assert toast(window, "Three.").count() == 1


def test_the_action_dismisses_then_runs(window):
    seen = []
    shown = toast(
        window,
        "Removed order 1001.",
        action_text="Undo",
        on_action=lambda: seen.append(Toast.for_window(window).isHidden()),
    )
    assert shown.button.text() == "Undo"
    shown.button.click()
    assert seen == [True]
    assert shown.isHidden()


def test_a_toast_raised_by_the_action_survives(window):
    shown = toast(
        window,
        "Removed order 1001.",
        action_text="Undo",
        on_action=lambda: toast(window, "Undone."),
    )
    shown.button.click()
    assert not shown.isHidden()
    assert shown.text() == "Undone."


def test_no_action_means_no_button(window):
    assert toast(window, "Done.").button.isHidden()


def test_it_stays_inside_the_window_after_a_resize(window):
    window.show()
    shown = toast(window, "Session S1 created.")
    window.resize(520, 400)
    QApplication.processEvents()
    assert window.rect().contains(shown.geometry())


@pytest.mark.parametrize("role", ["success", "info"])
def test_the_edge_carries_the_role_colour(window, role):
    shown = toast(window, "Done.", role=role)
    assert getattr(current_tokens(), f"status_{role}") in shown.styleSheet()


def test_a_failure_is_never_a_toast(window):
    with pytest.raises(ValueError):
        toast(window, "It broke.", role="danger")


def test_a_non_widget_source_is_refused(qapp):
    with pytest.raises(TypeError):
        toast(object(), "Done.")


def test_it_never_takes_focus(window):
    shown = toast(window, "Done.", action_text="Undo", on_action=lambda: None)
    assert shown.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert shown.button.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_the_edge_follows_a_theme_toggle(window):
    from gui.theme_manager import get_theme_manager

    manager = get_theme_manager()
    before = manager.get_current_theme().name
    shown = toast(window, "Done.")
    sheet = shown.styleSheet()
    try:
        manager.set_theme("dark" if before == "light" else "light")
        assert shown.styleSheet() != sheet
        assert current_tokens().status_success in shown.styleSheet()
    finally:
        manager.set_theme(before)
