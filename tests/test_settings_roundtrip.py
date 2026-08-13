"""Characterization test for SettingsWindow's config round-trip.

This is the safety net for the Track C structural split: it asserts that
building the window from a config and immediately saving returns that same
config. If a page extraction drops or renames a field, this fails.

Kept deliberately blunt -- it asserts on whole config sections rather than
individual widgets, so it keeps working as the pages move into gui/settings/.
"""
import copy
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from gui.settings.window import SettingsWindow


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def no_modals(monkeypatch):
    """Fail loudly instead of blocking forever.

    save_settings() reports validation failures through modal QMessageBox
    calls and returns early. Under the offscreen QPA platform an unstubbed
    modal hangs the test run, so every popup is recorded and dismissed.
    """
    seen = []
    for name in ("warning", "critical", "information", "question"):
        monkeypatch.setattr(
            QMessageBox, name,
            staticmethod(lambda *a, _n=name, **k: seen.append((_n, a[1:3]))),
        )
    return seen


def settings_fixture_config():
    """A config touching every section save_settings() writes."""
    return {
        "settings": {
            "stock_csv_delimiter": ";",
            "orders_csv_delimiter": ",",
            "low_stock_threshold": 5,
            "repeat_detection_days": 30,
        },
        "rules": [
            {
                "name": "Flag big orders",
                "priority": 1,
                "level": "order",
                "steps": [
                    {
                        "conditions": [
                            {"field": "item_count", "operator": "is greater than", "value": "5"}
                        ],
                        "match": "ALL",
                        "actions": [{"type": "ADD_ORDER_TAG", "value": "BULK"}],
                    }
                ],
            }
        ],
        "packing_list_configs": [
            {
                "name": "Main",
                "output_filename": "main.xlsx",
                "filters": [{"field": "SKU", "operator": "contains", "value": "AB"}],
                "exclude_skus": ["X1", "X2"],
            }
        ],
        "stock_export_configs": [
            {
                "name": "Daily",
                "output_filename": "daily.csv",
                "filters": [{"field": "Tags", "operator": "==", "value": "hot"}],
            }
        ],
        # v2 mappings are {csv_column: internal_name}. Every required internal
        # field must appear or save_settings() aborts at validation.
        "column_mappings": {
            "version": 2,
            "orders": {
                "Name": "Order_Number",
                "Lineitem sku": "SKU",
                "Lineitem quantity": "Quantity",
                "Shipping Method": "Shipping_Method",
                "Lineitem name": "Product_Name",
            },
            "stock": {"Article": "SKU", "Available": "Stock"},
        },
        "courier_mappings": {
            "DHL": {"patterns": ["dhl", "DHL Express"], "case_sensitive": False}
        },
        "set_decoders": {},
        "weight_config": {
            "volumetric_divisor": 5000,
            "products": {
                "SKU1": {
                    "name": "Widget",
                    "length_cm": 10.0,
                    "width_cm": 5.0,
                    "height_cm": 2.0,
                    "no_packaging": False,
                }
            },
            "boxes": [
                {"name": "Small", "length_cm": 20.0, "width_cm": 15.0, "height_cm": 10.0}
            ],
        },
        "tag_categories": {"version": 2, "categories": {}},
    }


@pytest.fixture
def started_workers(monkeypatch):
    """Intercept the background save instead of letting it run.

    save_settings() hands a Worker to QThreadPool.globalInstance().start().
    Left alone that really runs, on a real thread, racing the assertions and
    delivering a success QMessageBox through queued signals. Capturing the
    worker keeps the test deterministic and still proves the save was reached.
    """
    started = []
    monkeypatch.setattr(
        "gui.settings.window.QThreadPool",
        type("Pool", (), {
            "globalInstance": staticmethod(
                lambda: type("P", (), {"start": staticmethod(started.append)})()
            )
        }),
    )
    return started


@pytest.fixture
def window(qapp, no_modals, started_workers):
    """A real SettingsWindow with the background save intercepted."""
    win = SettingsWindow(
        client_id="M",
        client_config=settings_fixture_config(),
        profile_manager=Mock(),
    )
    yield win
    win.deleteLater()


def test_window_registers_every_page(window):
    assert list(window._page_index_by_name) == [
        "General", "Rules", "Packing Lists", "Stock Exports", "Mappings",
        "Sets", "Weight", "Tag Categories", "Column Config",
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
    """Round-tripping through save_settings() alone cannot see a dropped key.

    The shell merges dict-valued sections with `config_data[key].update(...)`,
    so a key the fixture already holds survives even if collect() stopped
    producing it. Compare each page's collect() output directly instead --
    every page owns disjoint top-level keys, so no merge is needed here.
    """
    before = copy.deepcopy(window.config_data)

    for page in window._pages:
        for section, value in page.collect().items():
            assert value == before[section], (
                f"{type(page).__name__}.collect() no longer reproduces "
                f"section {section!r}"
            )


def test_deleting_a_courier_row_survives_the_save_merge(window, no_modals):
    """Guards the live-reference contract MappingsPage depends on.

    `courier_mappings` holds a variable set of keys, and the shell's merge is
    `dict.update()`, which never drops one. MappingsPage only gets away with
    this because window.py hands it the *live* sub-dict, which it clears and
    refills in place. Hand it a copy instead and this test fails while every
    page-level test stays green.
    """
    mappings = window._pages[window._page_index_by_name["Mappings"]]
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


def test_a_key_no_page_renders_survives_a_save(qapp, no_modals, started_workers):
    """Live client configs on the server can carry keys this build's UI does
    not know about -- profile_migrations.py exists because that has happened.
    A page returning a fresh dict would drop them on every save."""
    config = settings_fixture_config()
    config["settings"]["legacy_key_no_page_renders"] = "keep me"
    config["weight_config"]["legacy_weight_key"] = 123

    win = SettingsWindow(client_id="M", client_config=config, profile_manager=Mock())
    win.save_settings()

    assert no_modals == [], f"save_settings() reported a problem: {no_modals}"
    assert win.config_data["settings"]["legacy_key_no_page_renders"] == "keep me"
    assert win.config_data["weight_config"]["legacy_weight_key"] == 123
    win.deleteLater()
