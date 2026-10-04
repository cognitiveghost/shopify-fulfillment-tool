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
        "Orders mapping",
        "Stock mapping",
        "Sets",
        "Weight",
        "Tag categories",
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
    (see gui/settings/contract.py), so for those two this compares an object
    to a deepcopy of itself and a dropped key still shows up. Their key
    coverage lives in test_settings_draft_general.py and
    test_settings_page_weight.py, which detach the page from the live dict
    first. Every other page builds a fresh dict, so this still bites for them.
    """
    before = copy.deepcopy(window.config_data)

    for page in window._pages:
        for section, value in page.collect().items():
            assert value == before[section], (
                f"{type(page).__name__}.collect() no longer reproduces "
                f"section {section!r}"
            )


def test_deleting_a_courier_row_survives_the_save_merge(window, no_modals):
    """Guards the live-reference contract OrdersDraft depends on.

    `courier_mappings` holds a variable set of keys, and the shell's merge is
    `dict.update()`, which never drops one. OrdersDraft only gets away with
    this because window.py hands it the *live* sub-dict, which it clears and
    refills in place. Hand it a copy instead and this test fails while every
    draft-level test stays green.
    """
    mappings = window._pages_by_name["Orders mapping"]
    while mappings.courier_rows:
        mappings.apply("courier_remove", ["0"])

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
    mappings = window._pages_by_name["Orders mapping"]
    monkeypatch.setattr(mappings, "validate", lambda: (False, ["Map the SKU column."]))

    window.save_settings()

    assert no_modals == []
    assert started_workers == []
    assert window._settings_nav.currentItem().text() == "Orders mapping"
    assert window._validation_message.text() == "Map the SKU column."
    assert not window._validation_message.isHidden()


def test_changing_page_clears_the_validation_message(window, monkeypatch):
    mappings = window._pages_by_name["Orders mapping"]
    monkeypatch.setattr(mappings, "validate", lambda: (False, ["Map the SKU column."]))
    window.save_settings()

    window._select_page("Sets")

    assert window._validation_message.isHidden()


def test_a_successful_save_says_so_in_the_footer_and_stays_open(window):
    closed = []
    window.finished.connect(closed.append)

    window.save_settings()
    window._on_save_settings_result(True)

    assert closed == []
    assert window._status_label.text() == "Saved. Applies from the next analysis."


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
    assert window.save_button.text() == "Save"


def test_a_crashed_write_points_to_logs(window, monkeypatch):
    errors = []
    monkeypatch.setattr(
        "gui.settings.window.show_error",
        lambda source, headline, what: errors.append((headline, what)),
    )
    window._on_save_settings_error((ValueError, ValueError("disk"), "tb"))
    assert errors == [("Settings weren't saved", "Details are in Logs.")]


def test_every_page_shares_one_widget_in_the_stack(window):
    """Every page is a draft: the stack shows one host for all of them, and
    the nav tells the host which to draw."""
    from gui.settings.window import WEB_PAGE_KEYS

    host = window._web_host
    assert window.tab_widget.count() == 1
    assert sorted(WEB_PAGE_KEYS) == sorted(window._pages_by_name)
    for name, key in WEB_PAGE_KEYS.items():
        window._select_page(name)
        assert window.tab_widget.currentWidget() is host
        assert host.bridge.state["page"] == key


def test_an_edit_on_a_web_page_marks_it_unsaved_at_once(window):
    window._select_page("General")
    window._web_host.bridge.edit("threshold", ["9"])
    assert window._unsaved == {"General"}
    window._web_host.bridge.edit("threshold", ["5"])
    assert window._unsaved == set()


def test_a_web_page_edit_is_what_gets_saved(window, no_modals, started_workers):
    window._select_page("Orders mapping")
    window._web_host.bridge.edit("courier_add", [])
    window._web_host.bridge.edit("courier_pattern", ["2", "evri"])
    window._web_host.bridge.edit("courier_code", ["2", "Evri"])
    window._select_page("General")
    window._web_host.bridge.edit("delimiter", ["orders", "tab"])

    window.save_settings()

    assert no_modals == []
    assert len(started_workers) == 1
    assert window.config_data["courier_mappings"]["Evri"] == {
        "patterns": ["evri"],
        "case_sensitive": False,
    }
    assert window.config_data["settings"]["orders_csv_delimiter"] == "\t"


def test_a_mapping_page_opens_with_the_file_loaded_on_setup(
    qapp, no_modals, started_workers, make_settings_config, tmp_path
):
    orders = tmp_path / "orders-30-09.csv"
    orders.write_text("Name,Lineitem sku\n#1,ABC\n", encoding="utf-8")
    win = SettingsWindow(
        client_id="M",
        client_config=make_settings_config(),
        profile_manager=Mock(),
        loaded_files={"orders": str(orders), "stock": str(tmp_path / "gone.csv")},
    )
    drafts = win._web_host.drafts
    assert drafts["orders"].file.name == "orders-30-09.csv"
    assert drafts["orders"].file.loaded is True
    assert drafts["orders"].file.columns == ("Name", "Lineitem sku")
    # A file that cannot be read is no file, and nothing is raised.
    assert drafts["stock"].file is None
    assert win.refresh_dirty() == []
    win.deleteLater()


def test_with_no_loaded_files_the_mapping_pages_have_no_file(window):
    assert window._web_host.drafts["orders"].file is None
    assert window._web_host.drafts["stock"].file is None
