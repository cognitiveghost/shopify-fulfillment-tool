import pytest

from gui.components.selectionbar import ContextualSelectionBar


def test_the_bar_starts_hidden(qapp):
    bar = ContextualSelectionBar()
    assert bar.isHidden()


def test_set_selection_shows_the_bar_with_the_callers_sentence(qapp):
    bar = ContextualSelectionBar()
    bar.set_selection("3 orders · 11 items selected")
    assert not bar.isHidden()
    assert bar.count_label.text() == "3 orders · 11 items selected"


def test_empty_selection_hides_the_bar_again(qapp):
    bar = ContextualSelectionBar()
    bar.set_selection("3 orders selected")
    bar.set_selection("")
    assert bar.isHidden()


def test_add_action_wires_the_slot(qapp):
    bar = ContextualSelectionBar()
    fired = []
    button = bar.add_action("Export CSV", lambda: fired.append(1))
    button.click()
    assert fired == [1]


def test_actions_default_to_secondary(qapp):
    bar = ContextualSelectionBar()
    button = bar.add_action("Export CSV", lambda: None)
    assert button.property("role") == "secondary"


def test_an_action_can_be_marked_danger(qapp):
    bar = ContextualSelectionBar()
    button = bar.add_action("Delete", lambda: None, role="danger")
    assert button.property("role") == "danger"


def test_an_unknown_role_raises(qapp):
    bar = ContextualSelectionBar()
    with pytest.raises(ValueError):
        bar.add_action("Nope", lambda: None, role="tertiary")


def test_the_bar_restyles_when_the_theme_changes(qapp):
    from gui.theme_manager import get_theme_manager

    bar = ContextualSelectionBar()
    before = bar.styleSheet()
    get_theme_manager().toggle_theme()
    try:
        assert bar.styleSheet() != before
    finally:
        get_theme_manager().toggle_theme()
