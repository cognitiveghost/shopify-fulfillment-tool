import json

import pytest

from shared import i18n
from shared.i18n import N_, _, _n


@pytest.fixture(autouse=True)
def english_after():
    yield
    i18n.set_language("en", [])


def _cat(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_english_is_the_key_and_the_fallback(tmp_path):
    assert _("Save") == "Save"
    i18n.set_language("bg", [_cat(tmp_path, "a.json", {"Save": "Запази"})])
    assert i18n.language() == "bg"
    assert _("Save") == "Запази"
    assert _("Not translated") == "Not translated"


def test_placeholders_are_filled_after_lookup(tmp_path):
    i18n.set_language("bg", [_cat(tmp_path, "a.json", {"{n} of {m}": "{n} от {m}"})])
    assert _("{n} of {m}", n=2, m=5) == "2 от 5"
    assert _("{n} left", n=3) == "3 left"


def test_text_without_values_is_not_formatted():
    assert _("Use {braces} literally") == "Use {braces} literally"


def test_plurals_pick_one_or_other(tmp_path):
    assert _n("{n} order", "{n} orders", 1) == "1 order"
    assert _n("{n} order", "{n} orders", 3) == "3 orders"
    i18n.set_language("bg", [_cat(tmp_path, "a.json", {"{n} order": ["{n} поръчка", "{n} поръчки"]})])
    assert _n("{n} order", "{n} orders", 1) == "1 поръчка"
    assert _n("{n} order", "{n} orders", 0) == "0 поръчки"


def test_later_files_win_and_missing_files_are_skipped(tmp_path):
    first = _cat(tmp_path, "a.json", {"Save": "A", "Close": "Затвори"})
    second = _cat(tmp_path, "b.json", {"Save": "Запази"})
    i18n.set_language("bg", [first, tmp_path / "missing.json", second])
    assert _("Save") == "Запази"
    assert _("Close") == "Затвори"


def test_a_corrupt_file_is_skipped_not_fatal(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    i18n.set_language("bg", [bad, _cat(tmp_path, "b.json", {"Save": "Запази"})])
    assert _("Save") == "Запази"


def test_unknown_language_falls_back_to_english(tmp_path):
    i18n.set_language("xx", [_cat(tmp_path, "a.json", {"Save": "?"})])
    assert i18n.language() == "en"
    assert _("Save") == "Save"
    assert i18n.catalogue() == {}


def test_english_loads_no_catalogue(tmp_path):
    i18n.set_language("en", [_cat(tmp_path, "a.json", {"Save": "?"})])
    assert _("Save") == "Save"


def test_n_marker_returns_text_unchanged():
    assert N_("Saved.") == "Saved."


def test_month_abbr_is_translated():
    assert i18n.month_abbr(1) == "Jan"
    assert i18n.month_abbr(12) == "Dec"
    i18n.set_language("bg", [i18n.SHARED_LOCALES / "bg.json"])
    assert i18n.month_abbr(10) == "окт"


def test_catalogue_files_are_shared_then_app(tmp_path):
    files = i18n.catalogue_files(tmp_path, "bg")
    assert files == [i18n.SHARED_LOCALES / "bg.json", tmp_path / "locales" / "bg.json"]


def test_languages_name_themselves():
    assert i18n.LANGUAGES == {"en": "English", "bg": "Български"}
