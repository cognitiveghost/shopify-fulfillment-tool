"""9.25: a confirm names its act, and Enter destroys nothing.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §4.2
"""

import pytest
from PySide6.QtWidgets import QDialogButtonBox

from shared.components.confirm_dialog import ConfirmDialog


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


def test_without_require_text_there_is_no_field_and_the_verb_is_live(qapp):
    dialog = _dialog()
    assert dialog.confirm_input is None
    assert dialog.verb_button.isEnabled()


def test_require_text_keeps_the_verb_off_until_the_exact_text_is_typed(qapp):
    dialog = ConfirmDialog(
        None,
        title="Delete CLIENT_X for good?",
        body="Gone.",
        verb="Delete",
        require_text="X",
    )
    assert dialog.confirm_input is not None
    assert dialog.confirm_input.placeholderText() == "Type X to confirm"
    assert not dialog.verb_button.isEnabled()
    dialog.confirm_input.setText("x")
    assert not dialog.verb_button.isEnabled()  # case-sensitive
    dialog.confirm_input.setText(" X ")
    assert dialog.verb_button.isEnabled()  # stripped
    dialog.confirm_input.setText("XY")
    assert not dialog.verb_button.isEnabled()
