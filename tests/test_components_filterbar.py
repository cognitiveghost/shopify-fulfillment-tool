import pytest

from gui.components.filterbar import FilterBar


def test_typing_emits_searchChanged(qapp):
    bar = FilterBar()
    seen = []
    bar.searchChanged.connect(seen.append)
    bar.search_field.setText("SKU-9")
    assert seen == ["SKU-9"]


def test_add_filter_shows_a_chip(qapp):
    bar = FilterBar()
    bar.add_filter("courier", "Courier: DPD")
    assert bar.filter_keys() == ["courier"]


def test_adding_the_same_key_twice_replaces_rather_than_duplicates(qapp):
    bar = FilterBar()
    bar.add_filter("courier", "Courier: DPD")
    bar.add_filter("courier", "Courier: DHL")
    assert bar.filter_keys() == ["courier"]


def test_dismissing_a_chip_emits_its_key_and_drops_it(qapp):
    bar = FilterBar()
    bar.add_filter("courier", "Courier: DPD")
    seen = []
    bar.filterRemoved.connect(seen.append)
    bar.chip("courier").click()
    assert seen == ["courier"]
    assert bar.filter_keys() == []


def test_remove_filter_is_silent_and_idempotent(qapp):
    bar = FilterBar()
    bar.add_filter("courier", "Courier: DPD")
    seen = []
    bar.filterRemoved.connect(seen.append)
    bar.remove_filter("courier")
    bar.remove_filter("courier")
    assert seen == []
    assert bar.filter_keys() == []


def test_set_count_shows_the_callers_text(qapp):
    bar = FilterBar()
    bar.set_count("41 of 212")
    assert bar.count_label.text() == "41 of 212"


def test_chip_raises_for_an_unknown_key(qapp):
    bar = FilterBar()
    with pytest.raises(KeyError):
        bar.chip("nope")
