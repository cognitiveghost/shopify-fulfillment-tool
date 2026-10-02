"""Everything the Tools page draws, built in one place (phase 5 spec section 4).

Python owns every fact and every sentence: tools_state() returns one dict and
gui/web/tools.js renders it. No Qt in this module, so the whole rule set runs
under plain pytest.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from datetime import datetime

from gui.setup_state import SessionFacts, session_meta
from shopify_tool.pdf_processor import READING, SAVING, STAMPING, reference_run_warning

MODES = ("driver", "raw_zpl")
# The QSettings scope each tool's print settings live under. They predate
# this page and must not change: every PC keeps what it has saved.
PRINT_SCOPE = {"reference": "reference_labels", "barcode": "barcode_generator"}

REFERENCE_SIZE_HINT = (
    "Physical label size as loaded in the printer, e.g. 152.4 x 101.6 for 6x4in "
    "shipping labels. 0 disables fitting and uses each page's own PDF size."
)
BARCODE_SIZE_HINT = (
    "Physical label size as loaded in the printer, e.g. 68 x 38 for this flow's "
    "default label stock. 0 disables fitting and uses the generated PDF's own page size."
)


@dataclass(frozen=True)
class PickedFile:
    """One picked input file, as its row shows it."""

    name: str
    count: int | None = None  # pages, or CSV rows; None with a problem
    problem: tuple[str, str] | None = None  # (title, text)


@dataclass(frozen=True)
class ToolRun:
    """A run in progress. total == 0 means the run has no count."""

    label: str
    done: int = 0
    total: int = 0
    cancelling: bool = False


@dataclass(frozen=True)
class ReferenceFacts:
    pdf: PickedFile | None = None
    csv: PickedFile | None = None
    folder: str = ""  # the output folder's full path; "" with no session
    open_pdf: bool = True
    run: ToolRun | None = None
    result: dict | None = None  # process_reference_labels' result for these inputs
    has_output: bool = False  # a processed PDF Print can send


@dataclass(frozen=True)
class PackingList:
    name: str
    count: int | None  # Fulfillable orders; None when the file can't be read
    has_labels: bool = False  # its barcode PDF is on disk
    has_qr: bool = False  # its QR PDF is on disk


@dataclass(frozen=True)
class BarcodeFacts:
    lists: tuple[PackingList, ...] = ()
    loading: bool = False
    analysed: bool = True  # the window holds analysis data
    selected: str = ""  # a list's name
    folder: str = ""  # the selected list's label folder; "" with none
    qr: bool = False
    open_pdf: bool = True
    run: ToolRun | None = None
    result: dict | None = None  # generate_list_labels' result


@dataclass(frozen=True)
class PrintFacts:
    settings: dict  # gui.pdf_printing.load_print_settings(scope)
    printers: tuple[str, ...] = ()  # installed printer names


def short_path(path: str) -> str:
    """A path's last two parts behind an ellipsis: "…\\2026-09-30_1\\barcodes"."""
    parts = [part for part in re.split(r"[\\/]+", str(path)) if part]
    return "…" + os.sep + os.sep.join(parts[-2:])


def _count(value: int, noun: str) -> str:
    return f"{value:,} {noun}{'' if value == 1 else 's'}"


def _row(pick: PickedFile | None, noun: str) -> dict:
    if pick is None:
        return {}
    if pick.problem is not None:
        title, text = pick.problem
        return {"name": pick.name, "meta": "Problem", "problem": {"title": title, "text": text}}
    return {"name": pick.name, "meta": _count(pick.count or 0, noun), "problem": {}}


def _folder(path: str, empty: str) -> dict:
    if not path:
        return {"text": empty, "title": "", "muted": True}
    return {"text": short_path(path), "title": path, "muted": False}


def _run(run: ToolRun | None) -> dict:
    """The running footer, worded. {} when idle."""
    if run is None:
        return {}
    if run.total <= 0:
        # Barcode: one render call, so a sentence and nothing to cancel.
        return {"label": run.label, "count": "", "bar": False, "percent": 0, "cancel": {}}
    saving = run.label == SAVING
    # One bar across both counted phases, so it never goes back.
    steps = {READING: run.done, STAMPING: run.total + run.done}.get(run.label, 2 * run.total)
    return {
        "label": "Saving…" if saving else run.label,
        "count": "" if saving else f"{run.done:,} of {run.total:,}",
        "bar": True,
        "percent": min(100, steps * 100 // (2 * run.total)),
        "cancel": {
            "label": "Cancelling…" if run.cancelling else "Cancel",
            "enabled": not saving and not run.cancelling,
            "title": "Saving can't be cancelled" if saving else "",
        },
    }


def _print_block(facts: PrintFacts, noun: str, size_hint: str) -> dict:
    settings = facts.settings
    mode = settings.get("print_mode")
    if mode not in MODES:
        mode = "driver"
    installed = list(facts.printers)

    if mode == "raw_zpl":
        current = str(settings.get("raw_zpl_target") or "").strip()
        options = [(name, name) for name in installed]
        printer = {
            "value": current,
            "label": current or "Choose a printer",
            "placeholder": not current,
        }
        if current:
            help_text, tone = (
                f"Sends {noun} straight to the label printer as ZPL, no dialog. "
                "Saved for this PC."
            ), ""
        else:
            help_text, tone = "Raw ZPL needs a printer. Choose the one the labels go to.", "danger"
        width = float(settings.get("raw_zpl_label_width_mm") or 0.0)
        height = float(settings.get("raw_zpl_label_height_mm") or 0.0)
        turned = bool(settings.get("raw_zpl_rotate"))
        inverted = bool(settings.get("raw_zpl_invert"))
        summary = f"{width:g} × {height:g} mm" if width > 0 and height > 0 else "the PDF's page size"
        if turned:
            summary += ", rotated 90°"
        if inverted:
            summary += ", colours inverted"
        setup = {
            "summary": summary,
            "target": current,
            "width": width,
            "height": height,
            "rotate": turned,
            "invert": inverted,
            "size_hint": size_hint,
        }
    else:
        current = str(settings.get("driver_printer_name") or "")
        options = [("", "Windows default")] + [(name, name) for name in installed]
        printer = {
            "value": current,
            "label": current or "Windows default",
            "placeholder": False,
        }
        help_text, tone = (
            f"Prints {noun} through the Windows print dialog. Saved for this PC."
        ), ""
        setup = {}

    # A saved printer this PC no longer lists is still the one in use.
    if current and current not in installed:
        options.append((current, current))
    return {
        "mode": mode,
        "printer": printer,
        "printers": [
            {"value": value, "label": label, "checked": value == current}
            for value, label in options
        ],
        "help": help_text,
        "help_tone": tone,
        "setup": setup,
    }


def _print_button(block: dict, *, base: str, has_pdf: bool, live: bool, missing: str) -> dict:
    """A print button: what it says, why, and whether it can be pressed."""
    zpl = block["mode"] == "raw_zpl"
    target = block["printer"]["value"] if zpl else ""
    if not has_pdf:
        title = missing
    elif zpl and not target:
        title = "Choose a printer under Print mode"
    elif zpl:
        title = f"Send to {target}"
    else:
        title = "Open the print dialog"
    return {
        "label": base if zpl else f"{base}…",
        "title": title,
        "enabled": has_pdf and live and (not zpl or bool(target)),
    }


def _matched(result: dict) -> str:
    pages = result.get("pages_processed", 0)
    matched = result.get("matched", 0)
    unmatched = result.get("unmatched", 0)
    by_name = result.get("name_matched", 0)
    text = f"{matched:,} of {pages:,} labels matched"
    if unmatched:
        text += f", {unmatched:,} unmatched"
    text += "."
    if by_name:
        text += f" {by_name:,} matched by name only."
    return text


def _reference(facts: ReferenceFacts, prints: PrintFacts, quiet: bool) -> dict:
    locked = facts.run is not None
    pdf_bad = facts.pdf is not None and facts.pdf.problem is not None
    csv_bad = facts.csv is not None and facts.csv.problem is not None
    pdf_ok = facts.pdf is not None and not pdf_bad
    csv_ok = facts.csv is not None and not csv_bad

    reason, tone = "", ""
    if quiet or locked:
        pass
    elif pdf_bad:
        reason, tone = "Fix the labels PDF to process.", "danger"
    elif csv_bad:
        reason, tone = "Fix the mapping CSV to process.", "danger"
    elif facts.pdf is None and facts.csv is None:
        reason = "Choose the labels PDF and mapping CSV."
    elif facts.pdf is None:
        reason = "Choose the labels PDF."
    elif facts.csv is None:
        reason = "Choose the mapping CSV."
    elif facts.result is not None:
        warning = reference_run_warning(facts.result)
        if warning:
            reason, tone = warning, "warning"
        else:
            reason = _matched(facts.result)
    else:
        reason = (
            f"{_count(facts.pdf.count or 0, 'page')}, "
            f"{_count(facts.csv.count or 0, 'CSV row')}."
        )

    block = _print_block(prints, "stamped labels", REFERENCE_SIZE_HINT)
    return {
        "quiet": quiet,
        "locked": locked,
        "pdf": _row(facts.pdf, "page"),
        "csv": _row(facts.csv, "row"),
        "folder": _folder("" if quiet else facts.folder, "Session folder"),
        "open_pdf": facts.open_pdf,
        "print": block,
        "run": _run(facts.run),
        "reason": reason,
        "tone": tone,
        "can_run": not quiet and not locked and pdf_ok and csv_ok and bool(facts.folder),
        "print_button": _print_button(
            block,
            base="Print",
            has_pdf=facts.has_output,
            live=not quiet and not locked,
            missing="Process labels first",
        ),
    }


def _barcode(facts: BarcodeFacts, prints: PrintFacts, quiet: bool) -> dict:
    locked = facts.run is not None
    lists = () if quiet else facts.lists
    cur = next((entry for entry in lists if entry.name == facts.selected), None)
    waiting = facts.loading and not lists
    folder = facts.folder if cur is not None else ""
    result = facts.result if cur is not None and facts.result is not None else None
    if result is not None and result.get("list") != cur.name:
        result = None

    if cur is not None:
        meta = "Unreadable" if cur.count is None else f"{cur.count:,} Fulfillable"
        shown = {"name": cur.name, "meta": meta, "placeholder": ""}
    elif waiting and not quiet:
        shown = {"name": "", "meta": "", "placeholder": "Reading packing lists…"}
    elif lists:
        shown = {"name": "", "meta": "", "placeholder": "Choose a packing list"}
    else:
        shown = {"name": "", "meta": "", "placeholder": "No packing lists"}

    reason, tone = "", ""
    if quiet or locked:
        pass
    elif waiting:
        reason = "Reading packing lists…"
    elif not lists:
        reason = "No packing lists in this session yet. Generate one on Results, then Refresh."
    elif not facts.analysed:
        reason = "This session has no analysis loaded. Run it on Setup."
    elif cur is None:
        reason = "Choose a packing list."
    elif cur.count is None:
        reason, tone = "This packing list couldn't be read. Details are in Logs.", "danger"
    elif cur.count == 0:
        reason = "No Fulfillable orders in this list."
    elif result is not None and result.get("failed"):
        reason, tone = (
            f"{_count(result.get('labels', 0), 'label')} written, "
            f"{_count(result['failed'], 'order number')} couldn't be encoded. "
            "Details are in Logs."
        ), "warning"
    elif result is not None and result.get("qr_failed"):
        reason, tone = (
            "Barcode labels written. The QR labels failed; details are in Logs."
        ), "warning"
    elif cur.has_labels:
        reason = f"Generating again replaces the labels in {short_path(folder)}."
    else:
        reason = f"Saves to {short_path(folder)}" + (", with QR labels." if facts.qr else ".")

    block = _print_block(prints, "barcode labels", BARCODE_SIZE_HINT)
    live = not quiet and not locked
    qr_button = {}
    if cur is not None and (facts.qr or cur.has_qr):
        qr_button = _print_button(
            block,
            base="Print QR labels",
            has_pdf=cur.has_qr,
            live=live,
            missing="Generate with QR labels ticked first",
        )
    empty = "Session folder" if quiet else "Choose a packing list"
    return {
        "quiet": quiet,
        "locked": locked,
        "list": shown,
        "lists": [
            {
                "name": entry.name,
                "meta": "—" if entry.count is None else f"{entry.count:,}",
                "checked": entry.name == facts.selected,
            }
            for entry in lists
        ],
        "folder": _folder(folder, empty),
        "qr": facts.qr,
        "open_pdf": facts.open_pdf,
        "print": block,
        "run": _run(facts.run),
        "reason": reason,
        "tone": tone,
        "can_run": live and facts.analysed and cur is not None and bool(cur.count),
        "print_button": _print_button(
            block,
            base="Print",
            has_pdf=cur is not None and cur.has_labels,
            live=live,
            missing="Generate this list's labels first",
        ),
        "qr_button": qr_button,
    }


def tools_state(
    *,
    client: str,
    session: SessionFacts | None,
    reference: ReferenceFacts,
    reference_print: PrintFacts,
    barcode: BarcodeFacts,
    barcode_print: PrintFacts,
    now: datetime,
) -> dict:
    """The one map the Tools page draws. Spec section 4.2."""
    quiet = session is None
    return {
        "session": (
            {} if quiet else {"name": session.name, "meta": session_meta(client, session, now)}
        ),
        "banner": quiet,
        "reference": _reference(reference, reference_print, quiet),
        "barcode": _barcode(barcode, barcode_print, quiet),
    }


def apply_print_edit(settings: dict, key: str, value) -> dict | None:
    """One print setting changed from the page (spec section 4.5).

    Returns the new settings, or None for an edit that is not one of the
    page's: the page is not trusted with a key or a type it was not given.
    """
    out = dict(settings)
    if key == "mode":
        if value not in MODES:
            return None
        out["print_mode"] = value
    elif key == "printer":
        if not isinstance(value, str):
            return None
        zpl = settings.get("print_mode") == "raw_zpl"
        out["raw_zpl_target" if zpl else "driver_printer_name"] = value
    elif key == "target":
        if not isinstance(value, str):
            return None
        out["raw_zpl_target"] = value.strip()
    elif key in ("width", "height"):
        # bool is an int in Python; the page never sends one for a size.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if math.isnan(value):
            return None
        out[f"raw_zpl_label_{key}_mm"] = round(min(500.0, max(0.0, float(value))), 1)
    elif key in ("rotate", "invert"):
        if not isinstance(value, bool):
            return None
        out[f"raw_zpl_{key}"] = value
    else:
        return None
    return out
