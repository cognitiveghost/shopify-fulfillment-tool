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


def test_clicking_the_current_item_again_emits_nothing(qapp):
    """The path self._current exists for: Qt has already flipped the group's
    checked state by the time clicked() runs, so checkedId() cannot see this."""
    rail = NavRail()
    rail.add_item("package", "Orders")
    rail.add_item("settings", "Settings")
    seen = []
    rail.currentChanged.connect(seen.append)
    rail.button(1).click()
    rail.button(1).click()
    assert seen == [1]


def test_a_footer_item_is_an_action_not_a_destination(qapp):
    rail = NavRail()
    rail.add_item("table", "Analysis Results")
    rail.add_item("wrench", "Tools")

    gear = rail.add_footer_item("settings", "Server Connection")

    assert not gear.isCheckable()
    assert rail._group.id(gear) == -1        # never joins the exclusive group
    assert not gear.icon().isNull()


def test_clicking_the_footer_leaves_the_destination_alone(qapp):
    rail = NavRail()
    rail.add_item("table", "Analysis Results")
    rail.add_item("wrench", "Tools")
    rail.set_current(1)
    seen = []
    rail.currentChanged.connect(seen.append)

    rail.add_footer_item("settings", "Server Connection").click()

    assert rail.current_index() == 1
    assert seen == []
    assert rail.button(1).isChecked()


def test_the_footer_sits_below_the_stretch(qapp):
    rail = NavRail()
    rail.add_item("table", "Analysis Results")
    gear = rail.add_footer_item("settings", "Server Connection")

    layout = rail.layout()
    stretch_at = next(
        i for i in range(layout.count()) if layout.itemAt(i).spacerItem() is not None
    )
    assert layout.indexOf(gear) > stretch_at


def test_footer_rejects_an_unknown_glyph(qapp):
    rail = NavRail()
    with pytest.raises(KeyError):
        rail.add_footer_item("not-a-real-icon", "nope")


def test_a_theme_toggle_restyles_the_rail(qapp):
    """A widget sheet outranks the app's, so a rail that bakes its colours in
    once stays light over dark pages."""
    from gui.theme_manager import get_theme_manager

    manager = get_theme_manager()
    rail = NavRail()
    before = rail.styleSheet()
    manager.toggle_theme()
    try:
        assert rail.styleSheet() != before
    finally:
        manager.toggle_theme()
