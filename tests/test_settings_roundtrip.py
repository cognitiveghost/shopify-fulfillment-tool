"""Characterization test for SettingsWindow's config round-trip.

This is the safety net for the Track C structural split: it asserts that
building the window from a config and immediately saving returns that same
config. If a page extraction drops or renames a field, this fails.

Kept deliberately blunt -- it asserts on whole config sections rather than
individual widgets, so it keeps working as the pages move into gui/settings/.

Fixtures (qapp, no_modals, started_workers, window, make_settings_config)
all come from conftest.py -- tests/ is not a package, so cross-file fixture
imports do not work.
"""

import copy
from unittest.mock import Mock

from gui.settings.window import SettingsWindow


def test_window_registers_every_page(window):
    assert list(window._page_index_by_name) == [
        "General",
        "Rules",
        "Reports",
        "Orders Mapping",
        "Stock Mapping",
        "Sets",
        "Weight",
        "Tag Categories",
    ]


def test_save_round_trips_every_config_section(window, no_modals):
    """Build from a config, save, get the same config back."""
    before = copy.deepcopy(window.config_data)

    window.save_settings()

    assert no_modals == [], f"save_settings() reported a problem: {no_modals}"
    for section in sorted(before):
        assert window.config_data[section] == before[section], (
            f"section {section!r} did not survive the round-trip"
        )


def test_no_page_silently_drops_a_field(window):
    """Compare each page's collect() output against the config it was built
    from, section by section.

    Blind spot to know about: General and Weight hold the *live* sub-dict
    (see gui/settings/base.py), so for those two this compares an object to
    a deepcopy of itself and a dropped key still shows up. Their key coverage
    lives in test_settings_page_{general,weight}.py, which detach the page
    from the live dict first. Every other page builds a fresh dict, so this
    still bites for them.
    """
    before = copy.deepcopy(window.config_data)

    for page in window._pages:
        for section, value in page.collect().items():
            assert value == before[section], (
                f"{type(page).__name__}.collect() no longer reproduces "
                f"section {section!r}"
            )


def test_deleting_a_courier_row_survives_the_save_merge(window, no_modals):
    """Guards the live-reference contract OrdersMappingPage depends on.

    `courier_mappings` holds a variable set of keys, and the shell's merge is
    `dict.update()`, which never drops one. OrdersMappingPage only gets away
    with this because window.py hands it the *live* sub-dict, which it clears
    and refills in place. Hand it a copy instead and this test fails while
    every page-level test stays green.
    """
    mappings = window._pages[window._page_index_by_name["Orders Mapping"]]
    for row_refs in list(mappings.courier_mapping_widgets):
        mappings._delete_courier_row(row_refs)

    window.save_settings()

    assert no_modals == [], f"save_settings() reported a problem: {no_modals}"
    assert window.config_data["courier_mappings"] == {}


def test_save_reaches_the_background_write(window, started_workers):
    """Guards the four gotchas above: had validation aborted early,
    save_settings() would have returned before queuing any worker."""
    window.save_settings()
    assert len(started_workers) == 1
    assert window._is_saving is True


def test_a_key_no_page_renders_survives_a_save(
    qapp, no_modals, started_workers, make_settings_config
):
    """Live client configs on the server can carry keys this build's UI does
    not know about -- profile_migrations.py exists because that has happened.
    A page returning a fresh dict would drop them on every save."""
    config = make_settings_config()
    config["settings"]["legacy_key_no_page_renders"] = "keep me"
    config["weight_config"]["legacy_weight_key"] = 123

    win = SettingsWindow(client_id="M", client_config=config, profile_manager=Mock())
    win.save_settings()

    assert no_modals == [], f"save_settings() reported a problem: {no_modals}"
    assert win.config_data["settings"]["legacy_key_no_page_renders"] == "keep me"
    assert win.config_data["weight_config"]["legacy_weight_key"] == 123
    win.deleteLater()


def test_a_validation_failure_selects_the_page_and_says_so_inline(
    window, no_modals, started_workers, monkeypatch
):
    mappings = window._pages_by_name["Orders Mapping"]
    monkeypatch.setattr(mappings, "validate", lambda: (False, ["Map the SKU column."]))

    window.save_settings()

    assert no_modals == []
    assert started_workers == []
    assert window._settings_nav.currentItem().text() == "Orders Mapping"
    assert window._validation_message.text() == "Map the SKU column."
    assert not window._validation_message.isHidden()


def test_changing_page_clears_the_validation_message(window, monkeypatch):
    mappings = window._pages_by_name["Orders Mapping"]
    monkeypatch.setattr(mappings, "validate", lambda: (False, ["Map the SKU column."]))
    window.save_settings()

    window._select_page("Sets")

    assert window._validation_message.isHidden()


def test_a_successful_save_toasts_on_the_parent_and_closes(window, monkeypatch):
    toasts = []
    monkeypatch.setattr(
        "gui.settings.window.toast", lambda source, text, **k: toasts.append(text)
    )
    accepted = []
    window.accepted.connect(lambda: accepted.append(True))

    window._on_save_settings_result(True)

    assert toasts == ["Settings saved"]
    assert accepted == [True]


def test_a_failed_write_shows_a_banner_and_stays_open(window, monkeypatch):
    errors = []
    monkeypatch.setattr(
        "gui.settings.window.show_error",
        lambda source, headline, what: errors.append((headline, what)),
    )
    accepted = []
    window.accepted.connect(lambda: accepted.append(True))

    window._on_save_settings_result(False)

    assert errors == [
        (
            "Settings weren't saved",
            (
                "The profile may be open on another PC, or the server can't be reached. "
                "Wait a few seconds, then press Save again."
            ),
        )
    ]
    assert accepted == []
    assert window.save_button.isEnabled()


def test_a_crashed_write_points_to_logs(window, monkeypatch):
    errors = []
    monkeypatch.setattr(
        "gui.settings.window.show_error",
        lambda source, headline, what: errors.append((headline, what)),
    )
    window._on_save_settings_error((ValueError, ValueError("disk"), "tb"))
    assert errors == [("Settings weren't saved", "Details are in Logs.")]
