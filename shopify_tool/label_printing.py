"""Raw ZPL printing for the Citizen CL-E300 thermal label printer.

Ported from barcode_tool's app/core/template_renderer.py (rasterization) and
app/core/zpl_print_service.py (ZPL encoding + RAW spooling) -- proven working
in production against the same hardware and the same 68mm x 38mm label
format this app's blabel templates already render at
(shopify_tool/barcode_processor.py). See
docs/superpowers/specs/2026-08-10-direct-label-printing-design.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image
from zebrafy import ZebrafyImage

# The Citizen CL-E300 print head is 203 dpi, so rasterizing at 203 maps one
# image pixel to one dot -- no resampling between here and the head. Thermal
# heads are bilevel, so the greyscale render is thresholded here (mode "1",
# no dithering) rather than left for the head to interpret.
PRINT_DPI = 203


def rasterize_pdf(pdf_path: Path, dpi: int = PRINT_DPI) -> list[Image.Image]:
    """Rasterize every page of pdf_path into a 1-bit PIL Image, one per label."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    images = []
    for page in pdf:
        bitmap = page.render(scale=dpi / 72, grayscale=True)
        images.append(bitmap.to_pil().convert("1", dither=Image.Dither.NONE))
    return images


def image_to_zpl(image: Image.Image, rotate: bool = False) -> str:
    # Raw ZPL talks straight to the print head - there's no driver in the
    # loop to reconcile a landscape-designed template against a
    # portrait-mounted label roll (or vice versa). rotate is an operator-set
    # fact about their specific printer's media, not derivable from the PDF.
    if rotate:
        image = image.transpose(Image.Transpose.ROTATE_90)
    # invert=True: PIL's mode "1" packs a set bit as white, but ZPL's ^GFA
    # graphic field treats a set bit as printed (black) - without this every
    # raw ZPL print comes out with barcode and background swapped.
    field = ZebrafyImage(image, invert=True, complete_zpl=False).to_zpl()
    return f"^XA\n^PW{image.width}\n^LL{image.height}\n{field}\n^XZ\n"


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


def print_pdf_raw_zpl(pdf_path: Path, target: str, rotate: bool = False) -> None:
    """Rasterize pdf_path and send each page as its own raw ZPL job to target
    (a Windows print-queue name, or a device path on Linux dev machines)."""
    for image in rasterize_pdf(pdf_path):
        data = image_to_zpl(image, rotate=rotate).encode("ascii")
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
