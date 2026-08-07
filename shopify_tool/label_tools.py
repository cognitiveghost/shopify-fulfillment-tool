"""Vector barcode/QR rendering and text-fit helpers, exposed to blabel
templates as `label_tools`.

Ported from cognitiveghost/barcode_tool's app/core/label_tools.py, trimmed
to what this app's two label templates need. Not ported: datamatrix,
hiro_square, pil_to_html_imgdata, now -- other label modes barcode_tool
supports that this app doesn't need.
"""

from __future__ import annotations

import base64
from io import BytesIO

import qrcode
import qrcode.image.svg
from blabel.label_tools import barcode as _blabel_barcode
from blabel.label_tools import wrap

_SVG_DATA_URI = "data:image/svg+xml;charset=utf-8;base64,"

# JetBrains Mono (and any monospace) advances 0.6em per character -- see
# templates/assets/fonts/fonts.css, the only font these templates use.
_MONO_CHAR_WIDTH = 0.6


def barcode(data, **writer_options) -> str:
    """Vector Code-128 barcode as an <img src=...> SVG data URI, no
    human-readable text under the bars by default (the label template
    draws its own order_number caption from the record's own field).

    Thin wrapper around blabel's own blabel.label_tools.barcode(fmt="svg").
    Verified working for alphanumeric Code-128 data (order numbers
    containing '#'/'-' render correctly) -- the function's internal
    .zfill(constructor.digits) call is a no-op for Code128, whose `digits`
    class attribute is 0.
    """
    writer_options.setdefault("write_text", False)
    return _blabel_barcode(data, fmt="svg", **writer_options)


def qr_code(data, border: int = 2, **qr_code_params) -> str:
    """Vector QR code as an <img src=...> SVG data URI."""
    qr = qrcode.QRCode(
        border=border, image_factory=qrcode.image.svg.SvgPathImage, **qr_code_params
    )
    qr.add_data(str(data))
    buffer = BytesIO()
    qr.make_image().save(buffer)
    return _SVG_DATA_URI + base64.b64encode(buffer.getvalue()).decode()


def fit_font_block(
    text,
    box_width_mm: float,
    box_height_mm: float,
    max_mm: float,
    min_mm: float = 2.0,
    line_height: float = 1.25,
) -> float:
    """Largest font size (mm) at which wrapped `text` still fits the box.

    Assumes a monospace font (see _MONO_CHAR_WIDTH) for a cheap
    character-count width estimate instead of real glyph measurement --
    correct for JetBrains Mono, the only font these templates bundle.
    """
    text = str(text or "")
    if not text:
        return max_mm
    size = max_mm
    while size > min_mm:
        chars_per_line = max(1, int(box_width_mm / (size * _MONO_CHAR_WIDTH)))
        lines = sum(
            len(wrap(part, chars_per_line).splitlines()) or 1
            for part in text.splitlines()
        ) or 1
        if lines * size * line_height <= box_height_mm:
            break
        size = round(size - 0.1, 2)
    return max(size, min_mm)
