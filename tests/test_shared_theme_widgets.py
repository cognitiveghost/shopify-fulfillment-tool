"""StatusDot / StatusChip resolve tokens by name, never by hex string."""
import pytest
from conftest import _rule_block

from shared.theme import (
    DARK_THEME,
    LIGHT_THEME,
    StatusChip,
    StatusDot,
    build_stylesheet,
)


def test_status_dot_resolves_role_from_tokens(qapp):
    dot = StatusDot("status_success", DARK_THEME)
    assert dot.color().name().upper() == DARK_THEME.status_success.upper()
    assert dot.width() == 10 and dot.height() == 10


def test_status_dot_accepts_any_token_field_not_only_status_roles(qapp):
    # STATUS_CONFIG maps "not_started" to text_secondary, which is not a status role.
    dot = StatusDot("text_secondary", DARK_THEME)
    assert dot.color().name().upper() == DARK_THEME.text_secondary.upper()


def test_status_dot_rejects_a_typo_at_construction(qapp):
    with pytest.raises(AttributeError):
        StatusDot("status_sucess", DARK_THEME)


def test_status_dot_set_role_reresolves_against_the_given_theme(qapp):
    dot = StatusDot("status_danger", DARK_THEME)
    dot.set_role("status_danger", LIGHT_THEME)
    assert dot.color().name().upper() == LIGHT_THEME.status_danger.upper()


def test_status_dot_no_longer_accepts_a_hex_string(qapp):
    with pytest.raises(AttributeError):
        StatusDot("#FF0000", DARK_THEME)


def test_status_chip_chip_variant_uses_the_role_tint(qapp):
    chip = StatusChip("status_success", "Completed", DARK_THEME)
    sheet = chip.styleSheet()
    assert chip.text() == "Completed"
    assert DARK_THEME.status_success_bg in sheet
    assert DARK_THEME.status_success in sheet


def test_status_chip_falls_back_to_surface_sunken_when_no_tint_exists(qapp):
    # text_secondary has no text_secondary_bg partner.
    chip = StatusChip("text_secondary", "Not Started", DARK_THEME)
    assert DARK_THEME.surface_sunken in chip.styleSheet()


def test_status_chip_edge_variant_draws_a_left_border_and_no_fill(qapp):
    chip = StatusChip("status_warning", "Paused", DARK_THEME, variant="edge")
    sheet = chip.styleSheet()
    assert f"border-left: 3px solid {DARK_THEME.status_warning}" in sheet
    assert "background-color: transparent" in sheet


def test_status_chip_rejects_an_unknown_variant(qapp):
    with pytest.raises(ValueError):
        StatusChip("status_info", "Active", DARK_THEME, variant="pill")


def test_status_chip_rejects_a_role_typo(qapp):
    with pytest.raises(AttributeError):
        StatusChip("status_wrning", "Paused", DARK_THEME)


def test_status_chip_set_status_reresolves(qapp):
    chip = StatusChip("status_info", "Active", DARK_THEME)
    chip.set_status("status_danger", "Incomplete", LIGHT_THEME)
    assert chip.text() == "Incomplete"
    assert LIGHT_THEME.status_danger in chip.styleSheet()


def test_a_live_chip_is_tinted_and_a_resting_one_is_not(qapp):
    from shared.theme import StatusChip

    live = StatusChip("status_warning", "Paused", DARK_THEME, live=True)
    resting = StatusChip("status_success", "Completed", DARK_THEME, live=False)
    assert DARK_THEME.status_warning_bg in live.styleSheet()
    assert "background-color: transparent" in resting.styleSheet()


def test_both_fill_states_keep_the_same_outline(qapp):
    from shared.theme import StatusChip

    live = StatusChip("status_info", "Active", DARK_THEME, live=True)
    resting = StatusChip("status_info", "Active", DARK_THEME, live=False)
    outline = f"border: 1px solid {DARK_THEME.status_info}"
    assert outline in live.styleSheet()
    assert outline in resting.styleSheet()


def test_the_chip_reserves_room_for_its_mark(qapp):
    from shared.theme import MARK_LEFT_PX, MARK_PX, StatusChip

    chip = StatusChip("status_info", "Active", DARK_THEME)
    assert f"padding: 2px 8px 2px {MARK_LEFT_PX + MARK_PX + 4}px" in chip.styleSheet()


def test_the_edge_variant_is_untouched_by_the_flags(qapp):
    from shared.theme import StatusChip

    edge = StatusChip("status_warning", "Paused", DARK_THEME, variant="edge",
                      live=False, manual=True)
    assert "border-left: 3px solid" in edge.styleSheet()
    assert "padding: 2px 8px;" in edge.styleSheet()


def test_a_hollow_dot_differs_from_a_solid_one(qapp):
    from shared.theme import StatusDot

    solid = StatusDot("status_success", DARK_THEME, filled=True)
    hollow = StatusDot("status_success", DARK_THEME, filled=False)
    assert solid._filled and not hollow._filled
    hollow.set_filled(True)
    assert hollow._filled


def test_todays_call_sites_are_unchanged_by_the_defaults(qapp):
    from shared.theme import StatusChip, StatusDot

    # live=True, manual=False reproduce the shipped tinted pill and solid dot,
    # so packing-tool's own screens do not move.
    chip = StatusChip("status_info", "Active", DARK_THEME)
    assert DARK_THEME.status_info_bg in chip.styleSheet()
    assert StatusDot("status_info", DARK_THEME)._filled


def test_regions_group_by_plane_not_by_outline():
    """F1: eleven outlines in one composition meant nothing was grouped,
    because everything was."""
    sheet = build_stylesheet(LIGHT_THEME)

    for rule in ("QTableView", "QListWidget", "QGroupBox", "QToolBar",
                 "QHeaderView::section"):
        block = _rule_block(sheet, rule)
        assert f"border: 1px solid {LIGHT_THEME.border}" not in block, (
            f"{rule} still outlines itself"
        )


def test_borders_stay_where_they_carry_meaning():
    """An input's edge and a hit target's edge are information."""
    sheet = build_stylesheet(LIGHT_THEME)
    for rule in ("QLineEdit", "QComboBox", "QPushButton"):
        assert "border: 1px solid" in _rule_block(sheet, rule)


def test_groupbox_and_card_share_one_radius():
    """radius_lg is dialogs only."""
    sheet = build_stylesheet(LIGHT_THEME)
    assert f"border-radius: {LIGHT_THEME.radius_md}px" in _rule_block(sheet, "QGroupBox")
