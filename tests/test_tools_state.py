"""Everything the Tools page draws, built from plain facts (phase 5 spec section 4)."""

import os
from datetime import datetime

import pytest

from gui.setup_state import SessionFacts
from gui.tools_state import (
    BARCODE_SIZE_HINT,
    REFERENCE_SIZE_HINT,
    BarcodeFacts,
    PackingList,
    PickedFile,
    PrintFacts,
    ReferenceFacts,
    ToolRun,
    apply_print_edit,
    short_path,
    tools_state,
)
from shopify_tool.pdf_processor import READING, SAVING, STAMPING

NOW = datetime(2026, 9, 30, 15, 0).astimezone()
OPENED = datetime(2026, 9, 30, 14, 2).astimezone()
SESSION = SessionFacts("2026-09-30_1", OPENED, None)
SEP = os.sep
REF_FOLDER = SEP.join(["", "srv", "ACME", "2026-09-30_1", "reference_labels"])
DHL_FOLDER = SEP.join(["", "srv", "ACME", "2026-09-30_1", "barcodes", "DHL"])

DRIVER = {
    "print_mode": "driver",
    "raw_zpl_target": "",
    "raw_zpl_rotate": False,
    "raw_zpl_invert": False,
    "raw_zpl_label_width_mm": 0.0,
    "raw_zpl_label_height_mm": 0.0,
    "driver_printer_name": "",
}
ZPL = {**DRIVER, "print_mode": "raw_zpl", "raw_zpl_target": "Zebra ZD421"}
PRINTERS = ("Zebra ZD421", "HP LaserJet")

PDF = PickedFile("dhl-labels-30-09.pdf", 120)
CSV = PickedFile("acme-refs-30-09.csv", 120)
BAD_CSV = PickedFile(
    "acme-refs-30-09.csv", None, ("This CSV has no usable rows", "Each row needs…")
)
BAD_PDF = PickedFile("dhl.pdf", None, ("This PDF can't be read", "Check that it isn't damaged…"))

LISTS = (
    PackingList("DHL", 120),
    PackingList("DPD", 48),
    PackingList("Royal Mail", 31),
)


def reference(**over):
    """The mockup's Ready state for Reference labels."""
    facts = {"pdf": PDF, "csv": CSV, "folder": REF_FOLDER}
    facts.update(over)
    return ReferenceFacts(**facts)


def barcode(**over):
    """The mockup's Ready state for Barcode labels."""
    facts = {"lists": LISTS, "selected": "DHL", "folder": DHL_FOLDER}
    facts.update(over)
    return BarcodeFacts(**facts)


def make_state(**over):
    """tools_state with the mockup's Ready state as the default."""
    facts = {
        "client": "ACME",
        "session": SESSION,
        "reference": reference(),
        "reference_print": PrintFacts(DRIVER, PRINTERS),
        "barcode": barcode(),
        "barcode_print": PrintFacts(ZPL, PRINTERS),
        "now": NOW,
    }
    facts.update(over)
    return tools_state(**facts)


# --- session and banner ------------------------------------------------------


def test_with_a_session_the_head_names_it_and_there_is_no_banner():
    state = make_state()
    assert state["session"] == {"name": "2026-09-30_1", "meta": "ACME · opened 14:02"}
    assert state["banner"] is False


def test_an_analysed_session_says_when():
    analysed = datetime(2026, 9, 30, 14, 6).astimezone()
    state = make_state(session=SessionFacts("2026-09-30_1", OPENED, analysed))
    assert state["session"]["meta"] == "ACME · analysed 14:06"


def test_with_no_session_the_banner_shows_and_both_cards_go_quiet():
    state = make_state(session=None, reference=ReferenceFacts(), barcode=BarcodeFacts())
    assert state["session"] == {}
    assert state["banner"] is True
    for card in (state["reference"], state["barcode"]):
        assert card["quiet"] is True
        assert card["reason"] == ""
        assert card["can_run"] is False
        assert card["print_button"]["enabled"] is False
        assert card["folder"] == {"text": "Session folder", "title": "", "muted": True}
    assert state["barcode"]["lists"] == []
    assert state["barcode"]["list"]["placeholder"] == "No packing lists"


def test_no_session_hides_facts_left_from_the_last_one():
    # The tools clear themselves on a session change; the state does not rely on it.
    state = make_state(session=None)
    assert state["reference"]["folder"]["muted"] is True
    assert state["barcode"]["lists"] == []
    assert state["barcode"]["qr_button"] == {}


# --- a short path -------------------------------------------------------------


def test_a_short_path_is_the_last_two_parts():
    assert short_path(REF_FOLDER) == f"…{SEP}2026-09-30_1{SEP}reference_labels"


def test_a_short_path_reads_a_windows_path_on_any_platform():
    assert short_path(r"\\fs01\fulfilment\ACME\2026-09-30_1\barcodes\DHL") == (
        f"…{SEP}barcodes{SEP}DHL"
    )


# --- reference labels ---------------------------------------------------------


def test_reference_ready():
    card = make_state()["reference"]
    assert card["pdf"] == {"name": "dhl-labels-30-09.pdf", "meta": "120 pages", "problem": {}}
    assert card["csv"] == {"name": "acme-refs-30-09.csv", "meta": "120 rows", "problem": {}}
    assert card["folder"] == {
        "text": f"…{SEP}2026-09-30_1{SEP}reference_labels",
        "title": REF_FOLDER,
        "muted": False,
    }
    assert (card["reason"], card["tone"]) == ("120 pages, 120 CSV rows.", "")
    assert card["can_run"] is True
    assert card["quiet"] is False and card["locked"] is False
    assert card["run"] == {}
    assert card["open_pdf"] is True


def test_one_page_and_one_row_are_singular_and_thousands_take_a_comma():
    card = make_state(
        reference=reference(pdf=PickedFile("a.pdf", 1), csv=PickedFile("a.csv", 1))
    )["reference"]
    assert (card["pdf"]["meta"], card["csv"]["meta"]) == ("1 page", "1 row")
    assert card["reason"] == "1 page, 1 CSV row."
    card = make_state(
        reference=reference(pdf=PickedFile("a.pdf", 1204), csv=PickedFile("a.csv", 1204))
    )["reference"]
    assert card["pdf"]["meta"] == "1,204 pages"
    assert card["reason"] == "1,204 pages, 1,204 CSV rows."


@pytest.mark.parametrize(
    ("over", "reason", "tone"),
    [
        ({"pdf": BAD_PDF}, "Fix the labels PDF to process.", "danger"),
        ({"csv": BAD_CSV}, "Fix the mapping CSV to process.", "danger"),
        ({"pdf": BAD_PDF, "csv": BAD_CSV}, "Fix the labels PDF to process.", "danger"),
        ({"pdf": None, "csv": None}, "Choose the labels PDF and mapping CSV.", ""),
        ({"pdf": None}, "Choose the labels PDF.", ""),
        ({"csv": None}, "Choose the mapping CSV.", ""),
    ],
)
def test_reference_says_what_is_missing_and_cannot_run(over, reason, tone):
    card = make_state(reference=reference(**over))["reference"]
    assert (card["reason"], card["tone"]) == (reason, tone)
    assert card["can_run"] is False


def test_a_problem_file_shows_its_problem_on_its_row():
    card = make_state(reference=reference(csv=BAD_CSV))["reference"]
    assert card["csv"] == {
        "name": "acme-refs-30-09.csv",
        "meta": "Problem",
        "problem": {"title": "This CSV has no usable rows", "text": "Each row needs…"},
    }
    assert make_state(reference=reference(csv=None))["reference"]["csv"] == {}


RESULT = {
    "output_file": "/out/labels.pdf",
    "pages_processed": 120,
    "matched": 120,
    "unmatched": 0,
    "duplicate_refs": [],
    "missing_refs": [],
    "name_matched": 0,
}


@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({}, "120 of 120 labels matched."),
        ({"matched": 118, "unmatched": 2}, "118 of 120 labels matched, 2 unmatched."),
        ({"name_matched": 3}, "120 of 120 labels matched. 3 matched by name only."),
        (
            {"matched": 118, "unmatched": 2, "name_matched": 3},
            "118 of 120 labels matched, 2 unmatched. 3 matched by name only.",
        ),
    ],
)
def test_after_a_run_the_reason_says_what_matched(over, reason):
    card = make_state(reference=reference(result={**RESULT, **over}, has_output=True))[
        "reference"
    ]
    assert (card["reason"], card["tone"]) == (reason, "")
    assert card["can_run"] is True


def test_a_run_that_needs_checking_keeps_its_warning_on_screen():
    result = {**RESULT, "duplicate_refs": ["12"], "missing_refs": ["14"]}
    card = make_state(reference=reference(result=result, has_output=True))["reference"]
    assert card["tone"] == "warning"
    assert card["reason"].startswith("Check before printing: ")
    assert "12" in card["reason"] and "14" in card["reason"]


def test_reference_needs_a_folder_to_run():
    assert make_state(reference=reference(folder=""))["reference"]["can_run"] is False


@pytest.mark.parametrize(
    ("run", "label", "count", "percent", "cancel"),
    [
        (ToolRun(READING, 0, 120), "Reading labels", "0 of 120", 0, True),
        (ToolRun(READING, 60, 120), "Reading labels", "60 of 120", 25, True),
        (ToolRun(READING, 120, 120), "Reading labels", "120 of 120", 50, True),
        (ToolRun(STAMPING, 40, 120), "Stamping labels", "40 of 120", 66, True),
        (ToolRun(STAMPING, 120, 120), "Stamping labels", "120 of 120", 100, True),
        (ToolRun(SAVING, 120, 120), "Saving…", "", 100, False),
    ],
)
def test_a_counted_run_draws_one_bar_that_never_goes_back(run, label, count, percent, cancel):
    card = make_state(reference=reference(run=run))["reference"]
    assert card["locked"] is True
    assert card["reason"] == ""
    assert card["can_run"] is False
    assert card["run"]["label"] == label
    assert card["run"]["count"] == count
    assert card["run"]["bar"] is True
    assert card["run"]["percent"] == percent
    assert card["run"]["cancel"]["enabled"] is cancel


def test_cancel_says_what_it_is_doing_and_why_it_cannot():
    going = make_state(reference=reference(run=ToolRun(STAMPING, 40, 120)))["reference"]
    assert going["run"]["cancel"] == {"label": "Cancel", "enabled": True, "title": ""}
    cancelling = make_state(
        reference=reference(run=ToolRun(STAMPING, 40, 120, cancelling=True))
    )["reference"]
    assert cancelling["run"]["cancel"] == {
        "label": "Cancelling…",
        "enabled": False,
        "title": "",
    }
    saving = make_state(reference=reference(run=ToolRun(SAVING, 120, 120)))["reference"]
    assert saving["run"]["cancel"] == {
        "label": "Cancel",
        "enabled": False,
        "title": "Saving can't be cancelled",
    }


def test_a_big_count_takes_commas():
    card = make_state(reference=reference(run=ToolRun(READING, 1200, 2400)))["reference"]
    assert card["run"]["count"] == "1,200 of 2,400"


def test_one_card_running_does_not_lock_the_other():
    state = make_state(reference=reference(run=ToolRun(READING, 1, 2)))
    assert state["reference"]["locked"] is True
    assert state["barcode"]["locked"] is False
    assert state["barcode"]["can_run"] is True


# --- barcode labels -----------------------------------------------------------


def test_barcode_ready():
    card = make_state()["barcode"]
    assert card["list"] == {"name": "DHL", "meta": "120 Fulfillable", "placeholder": ""}
    assert card["lists"] == [
        {"name": "DHL", "meta": "120", "checked": True},
        {"name": "DPD", "meta": "48", "checked": False},
        {"name": "Royal Mail", "meta": "31", "checked": False},
    ]
    assert card["folder"] == {
        "text": f"…{SEP}barcodes{SEP}DHL",
        "title": DHL_FOLDER,
        "muted": False,
    }
    assert (card["reason"], card["tone"]) == (f"Saves to …{SEP}barcodes{SEP}DHL.", "")
    assert card["can_run"] is True
    assert card["qr"] is False and card["open_pdf"] is True
    assert card["run"] == {}
    assert card["qr_button"] == {}


def test_with_qr_ticked_the_reason_says_so():
    card = make_state(barcode=barcode(qr=True))["barcode"]
    assert card["reason"] == f"Saves to …{SEP}barcodes{SEP}DHL, with QR labels."


def _dhl(**over):
    return (PackingList("DHL", **{"count": 120, **over}), *LISTS[1:])


@pytest.mark.parametrize(
    ("facts", "reason", "tone", "can_run"),
    [
        ({"lists": (), "selected": "", "loading": True}, "Reading packing lists…", "", False),
        (
            {"lists": (), "selected": ""},
            "No packing lists in this session yet. Generate one on Results, then Refresh.",
            "",
            False,
        ),
        (
            {"analysed": False, "lists": _dhl(count=None)},
            "This session has no analysis loaded. Run it on Setup.",
            "",
            False,
        ),
        ({"selected": ""}, "Choose a packing list.", "", False),
        (
            {"lists": _dhl(count=None)},
            "This packing list couldn't be read. Details are in Logs.",
            "danger",
            False,
        ),
        ({"lists": _dhl(count=0)}, "No Fulfillable orders in this list.", "", False),
        (
            {"result": {"list": "DHL", "labels": 118, "failed": 2}},
            "118 labels written, 2 order numbers couldn't be encoded. Details are in Logs.",
            "warning",
            True,
        ),
        (
            {"result": {"list": "DHL", "labels": 1, "failed": 1}},
            "1 label written, 1 order number couldn't be encoded. Details are in Logs.",
            "warning",
            True,
        ),
        (
            {"result": {"list": "DHL", "labels": 120, "failed": 0, "qr_failed": True}},
            "Barcode labels written. The QR labels failed; details are in Logs.",
            "warning",
            True,
        ),
        (
            {"lists": _dhl(has_labels=True)},
            f"Generating again replaces the labels in …{SEP}barcodes{SEP}DHL.",
            "",
            True,
        ),
    ],
)
def test_barcode_reasons(facts, reason, tone, can_run):
    card = make_state(barcode=barcode(**facts))["barcode"]
    assert (card["reason"], card["tone"]) == (reason, tone)
    assert card["can_run"] is can_run


def test_a_refresh_with_lists_on_screen_keeps_them_and_their_reason():
    card = make_state(barcode=barcode(loading=True))["barcode"]
    assert card["list"]["name"] == "DHL"
    assert card["reason"] == f"Saves to …{SEP}barcodes{SEP}DHL."


def test_a_result_for_another_list_says_nothing_about_this_one():
    card = make_state(barcode=barcode(result={"list": "DPD", "labels": 1, "failed": 9}))[
        "barcode"
    ]
    assert card["tone"] == ""


@pytest.mark.parametrize(
    ("facts", "shown"),
    [
        (
            {"lists": (), "selected": "", "loading": True},
            {"name": "", "meta": "", "placeholder": "Reading packing lists…"},
        ),
        (
            {"lists": (), "selected": ""},
            {"name": "", "meta": "", "placeholder": "No packing lists"},
        ),
        ({"selected": ""}, {"name": "", "meta": "", "placeholder": "Choose a packing list"}),
        (
            {"lists": _dhl(count=None)},
            {"name": "DHL", "meta": "Unreadable", "placeholder": ""},
        ),
        # Nothing was counted, which says nothing about the list.
        (
            {"lists": _dhl(count=None), "analysed": False},
            {"name": "DHL", "meta": "", "placeholder": ""},
        ),
    ],
)
def test_what_the_packing_list_select_shows(facts, shown):
    assert make_state(barcode=barcode(**facts))["barcode"]["list"] == shown


def test_an_unreadable_list_shows_a_dash_in_the_menu():
    card = make_state(barcode=barcode(lists=_dhl(count=None)))["barcode"]
    assert card["lists"][0] == {"name": "DHL", "meta": "—", "checked": True}


def test_with_no_list_chosen_the_folder_asks_for_one():
    card = make_state(barcode=barcode(selected="", folder=""))["barcode"]
    assert card["folder"] == {"text": "Choose a packing list", "title": "", "muted": True}


def test_a_barcode_run_is_a_sentence_with_no_bar_and_no_cancel():
    card = make_state(barcode=barcode(run=ToolRun("Writing 120 barcode labels…")))[
        "barcode"
    ]
    assert card["locked"] is True
    assert card["can_run"] is False
    assert card["reason"] == ""
    assert card["run"] == {
        "label": "Writing 120 barcode labels…",
        "count": "",
        "bar": False,
        "percent": 0,
        "cancel": {},
    }


# --- the print block ----------------------------------------------------------


def test_driver_mode_lists_windows_default_first():
    block = make_state()["reference"]["print"]
    assert block["mode"] == "driver"
    assert block["printer"] == {"value": "", "label": "Windows default", "placeholder": False}
    assert block["printers"] == [
        {"value": "", "label": "Windows default", "checked": True},
        {"value": "Zebra ZD421", "label": "Zebra ZD421", "checked": False},
        {"value": "HP LaserJet", "label": "HP LaserJet", "checked": False},
    ]
    assert block["help"] == (
        "Prints stamped labels through the Windows print dialog. Saved for this PC."
    )
    assert block["help_tone"] == ""
    assert block["setup"] == {}


def test_driver_mode_shows_its_saved_printer():
    saved = {**DRIVER, "driver_printer_name": "HP LaserJet"}
    block = make_state(reference_print=PrintFacts(saved, PRINTERS))["reference"]["print"]
    assert block["printer"]["label"] == "HP LaserJet"
    assert [p["checked"] for p in block["printers"]] == [False, False, True]


def test_raw_zpl_lists_the_installed_printers_and_its_setup():
    block = make_state()["barcode"]["print"]
    assert block["mode"] == "raw_zpl"
    assert block["printer"] == {
        "value": "Zebra ZD421",
        "label": "Zebra ZD421",
        "placeholder": False,
    }
    assert block["printers"] == [
        {"value": "Zebra ZD421", "label": "Zebra ZD421", "checked": True},
        {"value": "HP LaserJet", "label": "HP LaserJet", "checked": False},
    ]
    assert block["help"] == (
        "Sends barcode labels straight to the label printer as ZPL, no dialog. "
        "Saved for this PC."
    )
    assert block["setup"] == {
        "summary": "the PDF's page size",
        "target": "Zebra ZD421",
        "width": 0.0,
        "height": 0.0,
        "rotate": False,
        "invert": False,
        "size_hint": BARCODE_SIZE_HINT,
    }


def test_each_tool_carries_its_own_size_hint():
    state = make_state(reference_print=PrintFacts(ZPL, PRINTERS))
    assert state["reference"]["print"]["setup"]["size_hint"] == REFERENCE_SIZE_HINT


@pytest.mark.parametrize(
    ("over", "summary"),
    [
        ({}, "the PDF's page size"),
        ({"raw_zpl_label_width_mm": 152.4}, "the PDF's page size"),
        (
            {"raw_zpl_label_width_mm": 152.4, "raw_zpl_label_height_mm": 101.6},
            "152.4 × 101.6 mm",
        ),
        (
            {"raw_zpl_label_width_mm": 68.0, "raw_zpl_label_height_mm": 38.0},
            "68 × 38 mm",
        ),
        ({"raw_zpl_rotate": True}, "the PDF's page size, rotated 90°"),
        (
            {
                "raw_zpl_label_width_mm": 68.0,
                "raw_zpl_label_height_mm": 38.0,
                "raw_zpl_rotate": True,
                "raw_zpl_invert": True,
            },
            "68 × 38 mm, rotated 90°, colours inverted",
        ),
    ],
)
def test_the_label_setup_summary(over, summary):
    block = make_state(barcode_print=PrintFacts({**ZPL, **over}, PRINTERS))["barcode"]["print"]
    assert block["setup"]["summary"] == summary


def test_a_saved_printer_that_is_not_installed_is_still_listed():
    saved = {**ZPL, "raw_zpl_target": r"\\printsrv\zebra-3"}
    block = make_state(barcode_print=PrintFacts(saved, PRINTERS))["barcode"]["print"]
    assert block["printers"][-1] == {
        "value": r"\\printsrv\zebra-3",
        "label": r"\\printsrv\zebra-3",
        "checked": True,
    }
    driver = {**DRIVER, "driver_printer_name": "Old Canon"}
    block = make_state(reference_print=PrintFacts(driver, PRINTERS))["reference"]["print"]
    assert block["printers"][-1] == {"value": "Old Canon", "label": "Old Canon", "checked": True}


def test_raw_zpl_with_no_printer_says_so_in_the_danger_tone():
    block = make_state(barcode_print=PrintFacts({**ZPL, "raw_zpl_target": "  "}, PRINTERS))[
        "barcode"
    ]["print"]
    assert block["printer"] == {"value": "", "label": "Choose a printer", "placeholder": True}
    assert block["help"] == "Raw ZPL needs a printer. Choose the one the labels go to."
    assert block["help_tone"] == "danger"


def test_an_unknown_saved_mode_reads_as_driver():
    block = make_state(reference_print=PrintFacts({**DRIVER, "print_mode": "fax"}, ()))[
        "reference"
    ]["print"]
    assert block["mode"] == "driver"


def test_print_stays_live_with_no_session():
    state = make_state(session=None, reference=ReferenceFacts(), barcode=BarcodeFacts())
    assert state["reference"]["print"]["mode"] == "driver"
    assert state["barcode"]["print"]["setup"]["target"] == "Zebra ZD421"


# --- the print buttons --------------------------------------------------------


@pytest.mark.parametrize(
    ("settings", "has_output", "button"),
    [
        (DRIVER, False, {"label": "Print…", "title": "Process labels first", "enabled": False}),
        (DRIVER, True, {"label": "Print…", "title": "Open the print dialog", "enabled": True}),
        (ZPL, False, {"label": "Print", "title": "Process labels first", "enabled": False}),
        (ZPL, True, {"label": "Print", "title": "Send to Zebra ZD421", "enabled": True}),
        (
            {**ZPL, "raw_zpl_target": ""},
            True,
            {"label": "Print", "title": "Choose a printer under Print mode", "enabled": False},
        ),
    ],
)
def test_the_reference_print_button(settings, has_output, button):
    card = make_state(
        reference=reference(has_output=has_output),
        reference_print=PrintFacts(settings, PRINTERS),
    )["reference"]
    assert card["print_button"] == button


def test_print_is_off_while_its_card_runs():
    card = make_state(reference=reference(has_output=True, run=ToolRun(READING, 1, 2)))[
        "reference"
    ]
    assert card["print_button"]["enabled"] is False


def test_barcode_print_is_live_when_the_list_has_a_pdf_on_disk():
    off = make_state()["barcode"]["print_button"]
    assert off == {
        "label": "Print",
        "title": "Generate this list's labels first",
        "enabled": False,
    }
    on = make_state(barcode=barcode(lists=_dhl(has_labels=True)))["barcode"]["print_button"]
    assert on == {"label": "Print", "title": "Send to Zebra ZD421", "enabled": True}


@pytest.mark.parametrize(
    ("facts", "button"),
    [
        ({}, {}),
        (
            {"qr": True},
            {
                "label": "Print QR labels",
                "title": "Generate with QR labels ticked first",
                "enabled": False,
            },
        ),
        (
            {"lists": _dhl(has_qr=True)},
            {"label": "Print QR labels", "title": "Send to Zebra ZD421", "enabled": True},
        ),
        ({"qr": True, "selected": ""}, {}),
    ],
)
def test_the_qr_print_button(facts, button):
    assert make_state(barcode=barcode(**facts))["barcode"]["qr_button"] == button


def test_the_qr_button_takes_the_ellipsis_in_driver_mode():
    card = make_state(
        barcode=barcode(lists=_dhl(has_qr=True)), barcode_print=PrintFacts(DRIVER, PRINTERS)
    )["barcode"]
    assert card["qr_button"]["label"] == "Print QR labels…"
    assert card["print_button"]["label"] == "Print…"


# --- print edits --------------------------------------------------------------


def test_a_mode_edit():
    assert apply_print_edit(DRIVER, "mode", "raw_zpl")["print_mode"] == "raw_zpl"
    assert apply_print_edit(ZPL, "mode", "driver")["print_mode"] == "driver"
    assert apply_print_edit(DRIVER, "mode", "fax") is None


def test_a_printer_edit_writes_the_modes_own_key():
    assert apply_print_edit(DRIVER, "printer", "HP LaserJet")["driver_printer_name"] == (
        "HP LaserJet"
    )
    assert apply_print_edit(DRIVER, "printer", "HP LaserJet")["raw_zpl_target"] == ""
    out = apply_print_edit(ZPL, "printer", "HP LaserJet")
    assert out["raw_zpl_target"] == "HP LaserJet"
    assert out["driver_printer_name"] == ""
    assert apply_print_edit(DRIVER, "printer", 7) is None


def test_a_target_edit_is_stripped():
    assert apply_print_edit(ZPL, "target", "  /dev/usb/lp0 ")["raw_zpl_target"] == "/dev/usb/lp0"
    assert apply_print_edit(ZPL, "target", None) is None


@pytest.mark.parametrize(
    ("value", "stored"),
    [(152.4, 152.4), (68, 68.0), (0, 0.0), (-3, 0.0), (9999, 500.0), (101.64, 101.6)],
)
def test_a_size_edit_is_clamped_and_rounded(value, stored):
    assert apply_print_edit(ZPL, "width", value)["raw_zpl_label_width_mm"] == stored
    assert apply_print_edit(ZPL, "height", value)["raw_zpl_label_height_mm"] == stored


@pytest.mark.parametrize("value", [True, "68", None, float("nan")])
def test_a_size_edit_must_be_a_number(value):
    assert apply_print_edit(ZPL, "width", value) is None


def test_rotate_and_invert_must_be_bools():
    assert apply_print_edit(ZPL, "rotate", True)["raw_zpl_rotate"] is True
    assert apply_print_edit(ZPL, "invert", True)["raw_zpl_invert"] is True
    assert apply_print_edit(ZPL, "rotate", 1) is None
    assert apply_print_edit(ZPL, "invert", "yes") is None


def test_an_unknown_key_is_dropped_and_the_input_is_never_changed():
    before = dict(ZPL)
    assert apply_print_edit(ZPL, "print_mode", "driver") is None
    assert apply_print_edit(ZPL, "width", 68) is not ZPL
    assert before == ZPL
