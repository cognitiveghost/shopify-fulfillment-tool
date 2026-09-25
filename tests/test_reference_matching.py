import csv

from shopify_tool.pdf_processor import (
    load_csv_mapping,
    match_reference,
    reference_run_warning,
    reference_sort_key,
)


def mapping_for(tmp_path, rows):
    p = tmp_path / "m.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["postone", "tracking", "ref", "c3", "c4", "c5", "name"])
        for ref, name in rows:
            w.writerow(["", "", ref, "", "", "", name])
    return load_csv_mapping(p)


def test_cyrillic_name_does_not_match_a_longer_name(tmp_path):
    # Review Focus 3.
    m = mapping_for(tmp_path, [("100", "Иван Петров"), ("200", "Иван Петрова")])
    assert match_reference("Получател:\nИван Петрова\nСофия", m)["ref"] == "200"


def test_longest_nested_name_wins(tmp_path):
    m = mapping_for(tmp_path, [("100", "Ann Leeson"), ("200", "Ann Leeson Smith")])
    assert match_reference("To: Ann Leeson Smith", m)["ref"] == "200"


def test_two_unrelated_names_on_one_page_match_neither(tmp_path):
    m = mapping_for(tmp_path, [("100", "Maria Ivanova"), ("200", "Petar Georgiev")])
    assert match_reference("From Maria Ivanova to Petar Georgiev", m) is None


def test_a_repeated_row_is_not_ambiguous(tmp_path):
    m = mapping_for(tmp_path, [("100", "Maria Ivanova"), ("100", "Maria Ivanova")])
    assert match_reference("Maria Ivanova", m)["ref"] == "100"


def test_name_match_is_unverified(tmp_path):
    m = mapping_for(tmp_path, [("100", "Maria Ivanova")])
    assert match_reference("Maria Ivanova", m)["verified"] is False


def test_mapping_lists_every_reference(tmp_path):
    m = mapping_for(tmp_path, [("100", "Maria Ivanova"), ("", "No Ref"), ("200", "B B")])
    assert m["refs"] == {"100", "200"}


def test_numeric_refs_sort_by_value_and_others_after():
    refs = ["HW1ABC", "#10", "9", "#100", "ABC"]
    assert sorted(refs, key=reference_sort_key) == ["9", "#10", "#100", "ABC", "HW1ABC"]


def test_warning_names_duplicates_and_missing():
    result = {"duplicate_refs": ["100"], "missing_refs": ["200", "300"]}
    assert reference_run_warning(result) == (
        "Check before printing: REF 100 is on more than one page; no page for REF 200, 300.")


def test_warning_caps_long_lists():
    result = {"duplicate_refs": [], "missing_refs": [str(i) for i in range(1, 9)]}
    assert reference_run_warning(result) == (
        "Check before printing: no page for REF 1, 2, 3, 4, 5 (+3 more).")


def test_no_warning_for_a_clean_run():
    assert reference_run_warning({"duplicate_refs": [], "missing_refs": []}) is None
