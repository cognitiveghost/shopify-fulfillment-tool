"""Bundle 14's bridge members: every bulk verb and the toast."""

import pytest

from gui.results_bridge import ResultsBridge


@pytest.fixture
def bridge(qtbot):
    return ResultsBridge()


def _capture(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


def test_set_status_carries_the_orders_and_the_flag(bridge):
    seen = _capture(bridge.bulkStatusRequested)
    bridge.setStatus(["10443", 10444], True)
    assert seen == [(["10443", "10444"], True)]


def test_add_tag_carries_orders_and_tag(bridge):
    seen = _capture(bridge.bulkTagAddRequested)
    bridge.addTag(["10443"], "FRAGILE")
    assert seen == [(["10443"], "FRAGILE")]


def test_remove_tag_carries_orders_and_tag(bridge):
    seen = _capture(bridge.bulkTagRemovalRequested)
    bridge.removeTag(["10443"], "FRAGILE")
    assert seen == [(["10443"], "FRAGILE")]


def test_exclude_orders_carries_the_orders(bridge):
    seen = _capture(bridge.bulkExcludeRequested)
    bridge.excludeOrders(["10443", "10444"])
    assert seen == [(["10443", "10444"],)]


def test_sku_removals_carry_orders_and_sku(bridge):
    lines = _capture(bridge.bulkSkuRemovalRequested)
    orders = _capture(bridge.bulkOrderRemovalRequested)
    bridge.removeSkuFromOrders(["10443"], "TS-4409-B")
    bridge.removeOrdersWithSku(["10443"], "TS-4409-B")
    assert lines == [(["10443"], "TS-4409-B")]
    assert orders == [(["10443"], "TS-4409-B")]


@pytest.mark.parametrize("fmt", ["xlsx", "csv"])
def test_export_selection_passes_a_known_format(bridge, fmt):
    seen = _capture(bridge.bulkExportRequested)
    bridge.exportSelection(["10443"], fmt)
    assert seen == [(["10443"], fmt)]


def test_export_selection_drops_an_unknown_format(bridge):
    seen = _capture(bridge.bulkExportRequested)
    bridge.exportSelection(["10443"], "pdf")
    assert seen == []


def test_undo_is_a_bare_signal(bridge):
    seen = _capture(bridge.undoRequested)
    bridge.undo()
    assert seen == [()]


def test_undo_available_notifies_only_on_change(bridge):
    seen = _capture(bridge.undoAvailableChanged)
    assert bridge.undoAvailable is False
    bridge.set_undo_available(True)
    bridge.set_undo_available(True)
    assert bridge.undoAvailable is True
    assert len(seen) == 1


def test_raise_toast_emits_text_and_undoability(bridge):
    seen = _capture(bridge.toastRaised)
    bridge.raise_toast("3 orders held")
    bridge.raise_toast("FRAGILE added to 28 orders", undoable=True)
    assert seen == [("3 orders held", False), ("FRAGILE added to 28 orders", True)]
