"""Raw ZPL printing for the Citizen CL-E300 thermal label printer.

Ported from barcode_tool's app/core/template_renderer.py (rasterization) and
app/core/zpl_print_service.py (ZPL encoding + RAW spooling) -- proven working
in production against the same hardware and the same 68mm x 38mm label
format this app's blabel templates already render at
(shopify_tool/barcode_processor.py). See
docs/superpowers/specs/2026-08-10-direct-label-printing-design.md.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image
from zebrafy import ZebrafyImage

logger = logging.getLogger(__name__)

# The Citizen CL-E300 print head is 203 dpi, so rasterizing at 203 maps one
# image pixel to one dot -- no resampling between here and the head. Thermal
# heads are bilevel, so the greyscale render is thresholded here (mode "1",
# no dithering) rather than left for the head to interpret.
PRINT_DPI = 203


def rasterize_pdf(
    pdf_path: Path, dpi: int = PRINT_DPI, target_size_mm: tuple[float, float] | None = None
) -> list[Image.Image]:
    """Rasterize every page of pdf_path into a 1-bit PIL Image, one per label.

    Raw ZPL has no driver in the loop to reconcile a source page's own size
    against the physical label loaded in the printer -- ^PW/^LL just mirror
    whatever pixel dimensions we hand it (see image_to_zpl). Reference
    Labels source PDFs come from couriers and their page size is not
    trustworthy: the same batch PDF can mix pages from 98x147mm up to
    152x102mm. Left alone, a page smaller than the loaded media prints
    shrunk with blank margin instead of filling the label -- pass
    target_size_mm (the operator-configured physical label size) to resize
    every page to it, matching what OS print drivers already do implicitly
    when scaling a page to the selected paper size.
    """
    pdf = pdfium.PdfDocument(str(pdf_path))
    images = []
    for page in pdf:
        bitmap = page.render(scale=dpi / 72, grayscale=True)
        image = bitmap.to_pil()
        if target_size_mm is not None:
            width_mm, height_mm = target_size_mm
            target_px = (round(width_mm / 25.4 * dpi), round(height_mm / 25.4 * dpi))
            # Resize while still greyscale (LANCZOS) rather than after the
            # bilevel threshold below -- resizing a already-bilevel image
            # can only pick whole existing pixels (aliased jagged edges on
            # thin barcode bars), while resizing greyscale first blends
            # edges smoothly and *then* thresholds them to clean dots.
            image = image.resize(target_px, Image.Resampling.LANCZOS)
        images.append(image.convert("1", dither=Image.Dither.NONE))
    return images


def image_to_zpl(image: Image.Image, rotate: bool = False, invert: bool = False) -> str:
    # Raw ZPL talks straight to the print head - there's no driver in the
    # loop to reconcile a landscape-designed template against a
    # portrait-mounted label roll (or vice versa). rotate is an operator-set
    # fact about their specific printer's media, not derivable from the PDF.
    if rotate:
        image = image.transpose(Image.Transpose.ROTATE_90)
    # zebrafy >= 2.0 packs a set bit as a printed (black) dot when invert is
    # False. 1.2.x needed invert=True for the same output, so older zebrafy
    # prints inverted - hence the requirements floor. Our own invert is the
    # operator's "Invert colors" switch (see
    # docs/superpowers/specs/2026-09-29-minor-fixes-2-0-0-design.md).
    field = ZebrafyImage(image, invert=invert, complete_zpl=False).to_zpl()
    # ^LRN: label-reverse persists on the printer between jobs (and can be
    # saved to its memory), so reset it - each job's polarity is its own data.
    return f"^XA\n^LRN\n^PW{image.width}\n^LL{image.height}\n{field}\n^XZ\n"


def send_raw_windows(printer_name: str, data: bytes) -> None:
    import win32print

    handle = win32print.OpenPrinter(printer_name)
    try:
        win32print.StartDocPrinter(handle, 1, ("ZPL label", "", "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, data)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)


def send_raw_linux(device_path: str, data: bytes) -> None:
    Path(device_path).write_bytes(data)


def print_pdf_raw_zpl(
    pdf_path: Path,
    target: str,
    rotate: bool = False,
    target_size_mm: tuple[float, float] | None = None,
    invert: bool = False,
) -> None:
    """Rasterize pdf_path and send each page as its own raw ZPL job to target
    (a Windows print-queue name, or a device path on Linux dev machines).
    target_size_mm, if given, fits every page to that physical label size
    (see rasterize_pdf) before rotate is applied. invert flips black/white."""
    images = rasterize_pdf(pdf_path, target_size_mm=target_size_mm)
    if images:
        first = images[0]
        # A normal label is ~10-20% black; ~80-90% means the raster itself
        # came out inverted (render side), not the printer.
        black_pct = 100 * first.histogram()[0] / (first.width * first.height)
        logger.info(
            "Raw ZPL: %d label(s) to %s, first label %.0f%% black",
            len(images), target, black_pct,
        )
    for image in images:
        data = image_to_zpl(image, rotate=rotate, invert=invert).encode("ascii")
        if sys.platform == "win32":
            send_raw_windows(target, data)
        else:
            send_raw_linux(target, data)


def windows_print_errors() -> tuple[type[Exception], ...]:
    """Exception types raised by win32print, for UI-layer except clauses."""
    try:
        import pywintypes
    except ImportError:
        return ()
    return (pywintypes.error,)
