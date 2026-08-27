import pytest

from gui.components.navrail import RAIL_WIDTH, NavRail


def test_rail_is_the_spec_width(qapp):
    rail = NavRail()
    assert rail.width() == RAIL_WIDTH == 56


def test_add_item_returns_sequential_indices(qapp):
    rail = NavRail()
    assert rail.add_item("package", "Orders") == 0
    assert rail.add_item("settings", "Settings") == 1


def test_first_item_added_becomes_current(qapp):
    rail = NavRail()
    rail.add_item("package", "Orders")
    assert rail.current_index() == 0


def test_set_current_emits_currentChanged_once(qapp):
    rail = NavRail()
    rail.add_item("package", "Orders")
    rail.add_item("settings", "Settings")
    seen = []
    rail.currentChanged.connect(seen.append)
    rail.set_current(1)
    assert seen == [1]


def test_set_current_to_the_active_index_emits_nothing(qapp):
    rail = NavRail()
    rail.add_item("package", "Orders")
    rail.add_item("settings", "Settings")
    rail.set_current(1)
    seen = []
    rail.currentChanged.connect(seen.append)
    rail.set_current(1)
    assert seen == []


def test_clicking_an_item_emits_its_index(qapp):
    rail = NavRail()
    rail.add_item("package", "Orders")
    rail.add_item("settings", "Settings")
    seen = []
    rail.currentChanged.connect(seen.append)
    rail.button(1).click()
    assert seen == [1]


def test_set_current_rejects_an_out_of_range_index(qapp):
    rail = NavRail()
    rail.add_item("package", "Orders")
    with pytest.raises(IndexError):
        rail.set_current(3)


def test_an_unknown_icon_name_fails_at_add_time(qapp):
    rail = NavRail()
    with pytest.raises(KeyError):
        rail.add_item("no-such-glyph", "Nope")
