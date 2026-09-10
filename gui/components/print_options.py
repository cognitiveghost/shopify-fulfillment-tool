"""One tool's print settings, folded behind a row that states them.

Reference labels and Barcode labels each carried the same 80-line print block,
with every control always visible and four of five greyed out by mode. This is
that block once: the controls a mode does not use are hidden rather than
disabled, and the closed fold shows the current values, so nobody opens it to
check which printer is selected.

See docs/superpowers/specs/2026-09-10-phase9-bundle8-tools-inner-tabs-design.md §4.
"""


def print_summary(settings: dict) -> str:
    """The folded row's text: the current settings as one sentence."""
    if settings.get("print_mode") == "raw_zpl":
        target = (settings.get("raw_zpl_target") or "").strip()
        if not target:
            return "Raw ZPL needs a printer target. Open to set one."
        width = settings.get("raw_zpl_label_width_mm") or 0.0
        height = settings.get("raw_zpl_label_height_mm") or 0.0
        size = (
            f"{width:g} × {height:g} mm" if width and height else "the PDF's page size"
        )
        text = f"Prints raw ZPL to {target} at {size}"
        if settings.get("raw_zpl_rotate"):
            text += ", rotated 90°"
        return text
    printer = settings.get("driver_printer_name") or "the Windows default printer"
    return f"Prints through the print dialog to {printer}"
