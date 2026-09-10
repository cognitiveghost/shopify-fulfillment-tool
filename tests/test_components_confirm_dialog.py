"""9.25: a confirm names its act, and Enter destroys nothing.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §4.2
"""

import pytest
from gui.components.confirm_dialog import ConfirmDialog
from PySide6.QtWidgets import QDialogButtonBox


def _dialog(verb="Delete group"):
    return ConfirmDialog(
        None,
        title="Delete group North?",
        body="3 clients lose their group. This cannot be undone.",
        verb=verb,
    )


def test_the_accept_button_is_the_verb_and_is_primary(qapp):
    dialog = _dialog()
    assert dialog.verb_button.text() == "Delete group"
    assert (
        dialog.buttons.buttonRole(dialog.verb_button)
        == QDialogButtonBox.ButtonRole.AcceptRole
    )
    assert dialog.verb_button.property("role") == "primary"


def test_cancel_is_the_default_so_enter_destroys_nothing(qapp):
    dialog = _dialog()
    assert dialog.cancel_button.isDefault()
    assert not dialog.verb_button.isDefault()


@pytest.mark.parametrize("verb", ["OK", "yes", "Confirm", "continue"])
def test_a_verb_that_names_no_act_is_refused(qapp, verb):
    with pytest.raises(ValueError):
        _dialog(verb)


def test_the_title_and_body_are_shown(qapp):
    dialog = _dialog()
    assert dialog.windowTitle() == "Delete group North?"
    assert (
        dialog.body_label.text() == "3 clients lose their group. This cannot be undone."
    )


@pytest.mark.parametrize(("code", "expected"), [(1, True), (0, False)])
def test_ask_answers_with_the_dialog_result(qapp, monkeypatch, code, expected):
    monkeypatch.setattr(ConfirmDialog, "exec", lambda self: code)
    assert ConfirmDialog.ask(None, title="t", body="b", verb="Delete group") is expected
