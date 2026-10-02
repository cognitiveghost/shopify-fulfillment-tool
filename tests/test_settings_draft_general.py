"""GeneralDraft: the General page's values, with no widget (phase 7 spec section 4.2)."""

import pytest

from gui.settings.page_state import (
    DELIMITER_PROBLEM,
    THRESHOLD_PROBLEM,
    GeneralDraft,
)


def _draft(**stored):
    settings = {
        "stock_csv_delimiter": "auto",
        "orders_csv_delimiter": "auto",
        "low_stock_threshold": 5,
    }
    settings.update(stored)
    return GeneralDraft(settings, "ACME"), settings


def _delimiter(draft, kind):
    rows = {row["kind"]: row for row in draft.view()["general"]["delimiters"]}
    return rows[kind]


def _checked(draft, kind):
    return [o["value"] for o in _delimiter(draft, kind)["options"] if o["checked"]]


# --- what it opens with ------------------------------------------------------


def test_it_round_trips_its_settings_untouched():
    draft, settings = _draft(stock_csv_delimiter=";", orders_csv_delimiter=",")
    before = dict(settings)
    assert draft.collect() == {"settings": before}


def test_collect_updates_the_live_dict_and_keeps_keys_it_does_not_draw():
    """The window assigns collect()'s value over config_data["settings"]: a
    fresh dict would drop repeat_detection_days and anything a later build adds."""
    draft, settings = _draft(repeat_detection_days=30, delimiter_auto_migrated=True)
    draft.apply("threshold", ["9"])
    collected = draft.collect()["settings"]
    assert collected is settings
    assert settings["low_stock_threshold"] == 9
    assert settings["repeat_detection_days"] == 30
    assert settings["delimiter_auto_migrated"] is True


def test_missing_keys_fall_back_to_auto_and_five():
    draft = GeneralDraft({}, "ACME")
    assert draft.collect()["settings"] == {
        "stock_csv_delimiter": "auto",
        "orders_csv_delimiter": "auto",
        "low_stock_threshold": 5,
    }


@pytest.mark.parametrize(
    ("stored", "mode"),
    [("auto", "auto"), (",", "comma"), (";", "semicolon"), ("\t", "tab")],
)
def test_a_named_delimiter_opens_on_its_segment(stored, mode):
    draft, _settings = _draft(stock_csv_delimiter=stored)
    assert _checked(draft, "stock") == [mode]
    assert draft.delimiter("stock") == stored
    assert _delimiter(draft, "stock")["other"] is False


def test_pipe_opens_as_other_and_is_kept():
    draft, _settings = _draft(orders_csv_delimiter="|")
    assert _checked(draft, "orders") == ["other"]
    assert _delimiter(draft, "orders")["char"] == "|"
    assert draft.collect()["settings"]["orders_csv_delimiter"] == "|"


def test_a_hand_edited_value_survives_a_round_trip():
    draft, _settings = _draft(stock_csv_delimiter="||")
    assert draft.collect()["settings"]["stock_csv_delimiter"] == "||"
    assert draft.blocker() is None


# --- edits -------------------------------------------------------------------


def test_choosing_a_segment_changes_what_is_saved():
    draft, _settings = _draft()
    assert draft.apply("delimiter", ["orders", "semicolon"]) is True
    assert draft.collect()["settings"]["orders_csv_delimiter"] == ";"
    assert draft.collect()["settings"]["stock_csv_delimiter"] == "auto"


def test_other_takes_the_typed_character():
    draft, _settings = _draft()
    draft.apply("delimiter", ["stock", "other"])
    draft.apply("delimiter_char", ["stock", "|"])
    assert draft.collect()["settings"]["stock_csv_delimiter"] == "|"


def test_the_other_character_is_remembered_across_segments():
    draft, _settings = _draft(stock_csv_delimiter="|")
    draft.apply("delimiter", ["stock", "comma"])
    draft.apply("delimiter", ["stock", "other"])
    assert draft.delimiter("stock") == "|"


def test_the_threshold_is_saved_as_a_number():
    draft, _settings = _draft()
    draft.apply("threshold", [" 12 "])
    assert draft.collect()["settings"]["low_stock_threshold"] == 12


def test_an_edit_that_changes_nothing_reports_nothing():
    draft, _settings = _draft()
    assert draft.apply("delimiter", ["stock", "auto"]) is False
    assert draft.apply("threshold", ["5"]) is False
    assert draft.apply("delimiter_char", ["stock", ""]) is False


@pytest.mark.parametrize(
    ("action", "args"),
    [
        ("delimiter", ["stock", "pipe"]),
        ("delimiter", ["cats", "auto"]),
        ("delimiter", ["stock"]),
        ("delimiter", "stock"),
        ("delimiter_char", ["cats", "|"]),
        ("delimiter_char", ["stock", 7]),
        ("threshold", [5]),
        ("threshold", []),
        ("nope", []),
    ],
)
def test_an_edit_it_does_not_know_is_dropped(action, args):
    draft, settings = _draft()
    before = dict(settings)
    assert draft.apply(action, args) is False
    assert draft.collect()["settings"] == before


# --- what blocks a save ------------------------------------------------------


def test_nothing_blocks_a_fresh_page():
    draft, _settings = _draft()
    assert draft.blocker() is None
    assert draft.blocker_key() == ""
    assert draft.validate() == (True, [])


def test_other_with_no_character_blocks_the_save():
    draft, _settings = _draft()
    draft.apply("delimiter", ["orders", "other"])
    assert draft.blocker() == "Set Orders CSV delimiter"
    assert draft.blocker_key() == "char-orders"
    assert draft.validate() == (False, [f"Orders CSV delimiter: {DELIMITER_PROBLEM}"])
    row = _delimiter(draft, "orders")
    assert row["problem"] == DELIMITER_PROBLEM
    assert row["hint"] == ""


@pytest.mark.parametrize("text", ["", "abc", "-1", "2.5", "1 2"])
def test_a_threshold_that_is_not_a_whole_number_blocks_the_save(text):
    draft, _settings = _draft()
    draft.apply("threshold", [text])
    assert draft.blocker() == "Set Low-stock threshold"
    assert draft.blocker_key() == "threshold"
    assert draft.validate() == (False, [f"Low-stock threshold: {THRESHOLD_PROBLEM}"])
    assert draft.view()["general"]["threshold"]["problem"] == THRESHOLD_PROBLEM


def test_the_first_problem_on_the_page_is_the_one_named():
    draft, _settings = _draft()
    draft.apply("threshold", ["x"])
    draft.apply("delimiter", ["stock", "other"])
    assert draft.blocker() == "Set Stock CSV delimiter"
    assert len(draft.validate()[1]) == 2


def test_zero_is_a_threshold():
    draft, _settings = _draft()
    draft.apply("threshold", ["0"])
    assert draft.blocker() is None
    assert draft.collect()["settings"]["low_stock_threshold"] == 0


# --- unsaved -----------------------------------------------------------------


def test_an_edit_reads_unsaved_and_undoing_it_reads_clean():
    draft, _settings = _draft()
    draft.mark_clean()
    assert draft.is_dirty() is False
    draft.apply("delimiter", ["stock", "tab"])
    assert draft.is_dirty() is True
    draft.apply("delimiter", ["stock", "auto"])
    assert draft.is_dirty() is False


def test_a_half_typed_threshold_reads_unsaved():
    draft, _settings = _draft()
    draft.mark_clean()
    draft.apply("threshold", [""])
    assert draft.is_dirty() is True


# --- what the page draws -----------------------------------------------------


def test_the_view_names_the_page_and_the_client():
    view = _draft()[0].view()
    assert view["page"] == "general"
    assert view["title"] == "General"
    assert view["subtitle"] == (
        "How ACME's files are read, and when stock counts as low."
    )
    assert view["action"] == ""
    assert view["general"]["csv_text"] == (
        "The character that separates columns in ACME's files."
    )
    assert view["general"]["alerts_text"] == (
        "When a SKU is flagged as low stock in Results."
    )


def test_the_view_lists_stock_then_orders_with_five_segments_each():
    rows = _draft()[0].view()["general"]["delimiters"]
    assert [row["kind"] for row in rows] == ["stock", "orders"]
    assert [row["label"] for row in rows] == [
        "Stock CSV delimiter",
        "Orders CSV delimiter",
    ]
    assert [o["label"] for o in rows[0]["options"]] == [
        "Auto",
        "Comma",
        "Semicolon",
        "Tab",
        "Other",
    ]


@pytest.mark.parametrize(
    ("stored", "hint"),
    [
        ("auto", "Detected for each file as it is read."),
        (",", "Every file is split on commas."),
        (";", "Every file is split on semicolons."),
        ("\t", "Every file is split on tabs."),
        ("|", "Every file is split on “|”."),
    ],
)
def test_the_hint_says_how_files_are_split(stored, hint):
    draft, _settings = _draft(stock_csv_delimiter=stored)
    assert _delimiter(draft, "stock")["hint"] == hint


def test_the_threshold_view_carries_the_text_as_typed():
    draft, _settings = _draft()
    draft.apply("threshold", ["1x"])
    threshold = draft.view()["general"]["threshold"]
    assert threshold["value"] == "1x"
    assert threshold["unit"] == "units"
    assert threshold["hint"].startswith("A SKU is low when fewer than this are left")
