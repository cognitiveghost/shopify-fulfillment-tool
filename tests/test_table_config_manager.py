"""Regression test: applying column config must persist to client_config.json
in a single write, not two separate read-modify-write round trips (one for
the view, one for additional_columns) -- each was its own UNC-share round
trip on every Apply click.
"""
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication

from gui.table_config_manager import TableConfig, TableConfigManager


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def test_save_config_writes_view_and_additional_columns_in_one_call(profile_manager):
    profile_manager.create_client_profile("TESTCLIENT", "Test Client")
    tcm = TableConfigManager(main_window=Mock(), profile_manager=profile_manager)

    # A freshly created profile's config.json predates ui_settings/table_view,
    # so its first load auto-migrates and auto-saves once (see
    # ProfileManager.load_client_config). Prime that here, before installing
    # the spy, so the assertion below isolates save_config's own write count.
    profile_manager.load_client_config("TESTCLIENT")

    save_spy = Mock(wraps=profile_manager.save_client_config)
    profile_manager.save_client_config = save_spy

    config = TableConfig(visible_columns={"SKU": True}, column_order=["SKU"])
    additional_columns = [{"csv_name": "Extra", "internal_name": "extra", "enabled": True}]

    tcm.save_config("TESTCLIENT", config, "Default", additional_columns=additional_columns)

    assert save_spy.call_count == 1

    saved = profile_manager.load_client_config("TESTCLIENT")
    table_view = saved["ui_settings"]["table_view"]
    assert table_view["views"]["Default"]["column_order"] == ["SKU"]
    assert table_view["additional_columns"] == additional_columns


def test_save_config_without_additional_columns_leaves_existing_value_untouched(profile_manager):
    profile_manager.create_client_profile("TESTCLIENT", "Test Client")
    tcm = TableConfigManager(main_window=Mock(), profile_manager=profile_manager)

    seed = [{"csv_name": "Extra", "internal_name": "extra", "enabled": True}]
    tcm.save_config("TESTCLIENT", TableConfig(), "Default", additional_columns=seed)

    tcm.save_config("TESTCLIENT", TableConfig(visible_columns={"SKU": True}), "Default")

    saved = profile_manager.load_client_config("TESTCLIENT")
    assert saved["ui_settings"]["table_view"]["additional_columns"] == seed
