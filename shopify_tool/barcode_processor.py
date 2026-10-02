"""
Barcode Label Generator for Warehouse Operations.

Renders Code-128 barcode labels and QR labels for the Citizen CL-E300
thermal printer via blabel HTML/Jinja2 templates (shopify_tool/templates/),
label size 68mm x 38mm. See docs/superpowers/specs/2026-08-07-blabel-label-rendering-design.md.
"""

import json
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from blabel import LabelWriter

from shopify_tool import label_tools

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_FONTS_CSS = _TEMPLATES_DIR / "assets" / "fonts" / "fonts.css"
_BARCODE_LABEL_TEMPLATE = _TEMPLATES_DIR / "barcode_label" / "template.html"
_BARCODE_LABEL_STYLE = _TEMPLATES_DIR / "barcode_label" / "style.css"
_QR_LABEL_TEMPLATE = _TEMPLATES_DIR / "qr_label" / "template.html"
_QR_LABEL_STYLE = _TEMPLATES_DIR / "qr_label" / "style.css"


# === EXCEPTIONS ===
class BarcodeProcessorError(Exception):
    """Base exception for barcode processor."""


class InvalidOrderNumberError(BarcodeProcessorError):
    """Invalid order number for barcode encoding."""


class BarcodeGenerationError(BarcodeProcessorError):
    """Error during barcode generation."""


def barcode_pdf_path(barcodes_dir: Path, list_stem: str) -> Path:
    return Path(barcodes_dir) / f"{list_stem}_barcodes.pdf"


def qr_pdf_path(barcodes_dir: Path, list_stem: str) -> Path:
    return Path(barcodes_dir) / f"{list_stem}_qr_labels.pdf"


def barcodes_dir(session_path, list_stem: str) -> Path:
    """The folder holding a packing list's label PDFs."""
    return Path(session_path) / "barcodes" / list_stem


def invalidate_label_pdfs(session_path, list_stem: str) -> list[Path]:
    """Deletes a packing list's barcode and QR label PDFs. Called whenever
    the list is regenerated: a PDF left from before could label orders the
    new list no longer holds (AUDIT-04-12)."""
    folder = barcodes_dir(session_path, list_stem)
    removed = []
    for path in (barcode_pdf_path(folder, list_stem), qr_pdf_path(folder, list_stem)):
        if path.exists():
            path.unlink()
            removed.append(path)
    return removed


# === UTILITY FUNCTIONS ===

def sanitize_order_number(order_number: str) -> str:
    """
    Clean order number for Code-128 barcode encoding.

    Preserves alphanumeric characters, hyphens, underscores, and the '#' prefix
    used by Shopify order numbers (e.g. #1029392, #BG10129). Code-128 mode B
    supports the full printable ASCII range so '#' encodes reliably.

    Args:
        order_number: Raw order number

    Returns:
        Sanitized order number safe for barcode encoding

    Raises:
        InvalidOrderNumberError: If order number is empty after sanitization
    """
    if not order_number:
        raise InvalidOrderNumberError("Order number cannot be empty")

    if not order_number.isascii():
        raise InvalidOrderNumberError(
            f"Order number '{order_number}' has characters a Code-128 barcode can't carry"
        )

    clean = ''.join(c for c in order_number if c.isalnum() or c in ['-', '_', '#'])

    if not clean:
        raise InvalidOrderNumberError(f"Order number '{order_number}' contains no valid characters")

    return clean


def format_tags_for_barcode(internal_tag) -> str:
    """
    Format internal tags for barcode label display.

    Parses JSON array format and returns all tags pipe-separated.

    Args:
        internal_tag: Internal tag string (JSON array format: '["GIFT+1", "GIFT+2"]'),
            or a native list (Internal_Tags is sometimes stored unserialized).

    Returns:
        Formatted tag string with all tags pipe-separated

    Examples:
        >>> format_tags_for_barcode('["GIFT+1", "GIFT+2"]')
        "GIFT+1|GIFT+2"
        >>> format_tags_for_barcode("Priority")
        "Priority"
    """
    if isinstance(internal_tag, list):
        tags = [str(tag).strip() for tag in internal_tag if tag]
        return '|'.join(tag for tag in tags if tag)

    if isinstance(internal_tag, str):
        internal_tag = internal_tag.strip()

    if not internal_tag or internal_tag == 'nan' or internal_tag == 'None':
        return ""

    if internal_tag.startswith('[') and internal_tag.endswith(']'):
        tags_list = None
        try:
            tags_list = json.loads(internal_tag)
        except (json.JSONDecodeError, ValueError):
            try:
                import ast
                tags_list = ast.literal_eval(internal_tag)
            except (ValueError, SyntaxError):
                pass
        if isinstance(tags_list, list):
            return '|'.join(str(tag).strip() for tag in tags_list if tag)

    if '|' in internal_tag:
        tags = [t.strip() for t in internal_tag.split('|') if t.strip()]
        return '|'.join(tags)

    return internal_tag.strip()


# === BATCH RECORD BUILDING ===

def generate_barcodes_batch(
    df: pd.DataFrame,
    sequential_map: dict[str, int] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None
) -> list[dict[str, Any]]:
    """
    Build one label record per order, validating/sanitizing each order number.

    No rendering happens here -- pass the successful records to
    generate_code128_labels_pdf() to render the actual PDF.

    Args:
        df: DataFrame with columns:
            - Order_Number (required)
            - Shipping_Provider (required, courier name)
            - Destination_Country (required, may be empty)
            - Internal_Tag (required, may be empty)
            - item_count (preferred) or Quantity (fallback): number of items in order
        sequential_map: Dict mapping Order_Number to sequential number (from sequential_order.json)
                       If None, will use row index + 1 as fallback
        progress_callback: Optional callback(current, total, message) for progress updates

    Returns:
        List of result dicts (one per order). success=True results carry
        order_number (original), safe_order_number (barcode-safe, what the
        label actually shows/encodes), sequential_num, courier, country,
        tag, item_count -- ready to pass to generate_code128_labels_pdf().
        success=False results carry safe_order_number=None and an error.
    """
    results = []
    total_orders = len(df)

    logger.info(f"Starting batch barcode generation: {total_orders} orders")

    using_independent_numbering = sequential_map is None
    if using_independent_numbering:
        logger.info("Using independent packing list numbering (1, 2, 3...)")

    for idx, row in df.iterrows():
        order_number = "" if pd.isna(row['Order_Number']) else str(row['Order_Number'])
        if sequential_map:
            sequential_num = sequential_map.get(order_number, idx + 1)
        else:
            sequential_num = idx + 1

        if progress_callback:
            progress_callback(
                len(results) + 1,
                total_orders,
                f"Preparing barcode {len(results) + 1} of {total_orders}..."
            )

        try:
            safe_order_number = sanitize_order_number(order_number)
        except InvalidOrderNumberError as e:
            logger.exception(f"Invalid order number '{order_number}'")
            results.append({
                "order_number": order_number,
                "safe_order_number": None,
                "sequential_num": 0,
                "courier": "",
                "country": "N/A",
                "tag": "N/A",
                "item_count": 0,
                "success": False,
                "error": str(e)
            })
            continue

        courier = str(row['Shipping_Provider'])
        country = str(row.get('Destination_Country', '')) if pd.notna(row.get('Destination_Country')) else ''

        tag_raw = row.get('Internal_Tags', row.get('Internal_Tag', ''))
        tag = str(tag_raw) if pd.notna(tag_raw) and tag_raw else ''
        if tag and tag != 'nan' and tag != 'None':
            logger.info(f"Order {order_number}: Tag found = '{tag}'")

        raw_count = row.get('item_count')
        if pd.isna(raw_count):
            raw_count = row.get('Quantity', 1)
        try:
            # Do not use `raw_count or 1` -- a genuinely-zero item_count is
            # falsy in Python and would be wrongly coerced to 1.
            item_count = int(float(raw_count))
        except (ValueError, TypeError):
            item_count = 1

        results.append({
            "order_number": order_number,
            "safe_order_number": safe_order_number,
            "sequential_num": sequential_num,
            "courier": courier,
            "country": country if country else "N/A",
            "tag": format_tags_for_barcode(tag) or "N/A",
            "item_count": item_count,
            "success": True,
            "error": None
        })

    # Distinct order numbers that encode to one value would scan as each
    # other, here and in Packing Tool, which normalises harder still.
    # Refuse all of them rather than let a scan pick one (AUDIT-04-5).
    by_value: dict[str, list[dict]] = {}
    for r in results:
        if r["success"]:
            by_value.setdefault(r["safe_order_number"], []).append(r)
    for value, group in by_value.items():
        if len(group) < 2:
            continue
        for r in group:
            others = ", ".join(o["order_number"] for o in group if o is not r)
            r.update(success=False, safe_order_number=None,
                     error=f"Barcode value {value} would also scan as order(s) {others}")
            logger.error(f"Order {r['order_number']}: {r['error']}")

    logger.info(
        f"Batch preparation complete: {sum(r['success'] for r in results)}/{total_orders} successful"
    )
    return results


# === PDF RENDERING ===

def _check_page_count(pdf_bytes: bytes, expected: int) -> None:
    """Raises unless the rendered PDF has one page per label. A renderer
    that drops pages (WeasyPrint 69) must fail loudly, not print short."""
    from io import BytesIO

    import pypdf

    pages = len(pypdf.PdfReader(BytesIO(pdf_bytes)).pages)
    if pages != expected:
        raise BarcodeGenerationError(f"Label PDF has {pages} pages for {expected} labels")


def generate_code128_labels_pdf(orders: list[dict[str, Any]], output_pdf: Path) -> Path:
    """
    Render one Code-128 label per order as a single multi-page PDF.

    Args:
        orders: List of dicts as produced by generate_barcodes_batch()'s
            successful results: safe_order_number, sequential_num, courier,
            country, tag, item_count.
        output_pdf: Output PDF path.

    Returns:
        Path to the generated PDF (same as output_pdf).

    Raises:
        ValueError: If orders is empty.
        BarcodeGenerationError: If rendering fails.
    """
    if not orders:
        raise ValueError("Cannot generate PDF: no orders provided")

    date_str = datetime.now().astimezone().strftime("%d/%m/%y")
    records = [
        {
            "order_number": order["safe_order_number"],
            "sequential_num": order["sequential_num"],
            "courier": order["courier"],
            "country": order["country"],
            "tag": order["tag"],
            "item_count": order["item_count"],
            "date_str": date_str,
        }
        for order in orders
    ]

    try:
        writer = LabelWriter(
            str(_BARCODE_LABEL_TEMPLATE),
            default_stylesheets=(str(_FONTS_CSS), str(_BARCODE_LABEL_STYLE)),
            items_per_page=1,
            label_tools=label_tools,
        )
        pdf_bytes = writer.write_labels(records, target="@memory")
        _check_page_count(pdf_bytes, len(records))
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        output_pdf.write_bytes(pdf_bytes)
    except Exception as e:
        raise BarcodeGenerationError(f"Failed to generate barcode labels PDF: {e}") from e

    logger.info(f"Generated PDF: {output_pdf} ({len(records)} pages)")
    return output_pdf


def generate_qr_labels_pdf(orders: list[dict[str, Any]], output_pdf: Path) -> Path:
    """
    Render one QR label per order as a single multi-page PDF.

    Args:
        orders: List of dicts as produced by generate_barcodes_batch()'s
            successful results -- same shape generate_code128_labels_pdf()
            takes: safe_order_number, sequential_num, courier, country, tag,
            item_count. The QR code encodes the order number only.
        output_pdf: Output PDF path.

    Returns:
        Path to the generated PDF (same as output_pdf).

    Raises:
        ValueError: If orders is empty.
        BarcodeGenerationError: If rendering fails.
    """
    if not orders:
        raise ValueError("Cannot generate PDF: no orders provided")

    date_str = datetime.now().astimezone().strftime("%d/%m/%y")
    records = [
        {
            "order_number": order["safe_order_number"],
            "sequential_num": order["sequential_num"],
            "courier": order["courier"],
            "country": order["country"],
            "tag": order["tag"],
            "item_count": order["item_count"],
            "date_str": date_str,
        }
        for order in orders
    ]

    try:
        writer = LabelWriter(
            str(_QR_LABEL_TEMPLATE),
            default_stylesheets=(str(_FONTS_CSS), str(_QR_LABEL_STYLE)),
            items_per_page=1,
            label_tools=label_tools,
        )
        pdf_bytes = writer.write_labels(records, target="@memory")
        _check_page_count(pdf_bytes, len(records))
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        output_pdf.write_bytes(pdf_bytes)
    except Exception as e:
        raise BarcodeGenerationError(f"Failed to generate QR labels PDF: {e}") from e

    logger.info(f"Generated QR labels PDF: {output_pdf} ({len(records)} pages)")
    return output_pdf


# === ONE PACKING LIST, START TO FINISH ===

def packing_list_orders(xlsx_path) -> frozenset:
    """The order numbers a packing list workbook holds, as pandas reads them.

    Raises:
        ValueError: If the sheet has no Order_Number column.
    """
    frame = pd.read_excel(xlsx_path)
    if "Order_Number" not in frame.columns:
        raise ValueError(f"Packing list has no Order_Number column: {xlsx_path}")
    return frozenset(frame["Order_Number"].dropna().unique())


def _writing(count: int, kind: str) -> str:
    return f"Writing {count:,} {kind} label{'' if count == 1 else 's'}…"


def generate_list_labels(
    orders_df: pd.DataFrame,
    folder,
    list_stem: str,
    *,
    qr: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Write one packing list's label PDFs: the barcode labels, and with
    `qr` the QR labels beside them.

    Everything slow is in here, so a caller runs it on a worker thread
    (phase 5 spec section 7.2). `progress` is told one sentence before each
    render; a render is a single WeasyPrint call and reports nothing itself.

    Args:
        orders_df: The Fulfillable rows of the orders on this list, one row
            per order line (Order_Number, Quantity, Shipping_Provider, ...).
        folder: Where the PDFs go (barcodes_dir(session, list_stem)).
        list_stem: The packing list's name; it names the PDFs.

    Returns:
        {"list", "folder", "labels": labels written, "failed": orders whose
        number could not be encoded, "pdf": path or None, "qr_pdf": path or
        None, "qr_failed": bool}

    Raises:
        BarcodeGenerationError: If the barcode PDF cannot be rendered. A QR
            failure is logged and reported as qr_failed; the barcode PDF stands.
    """
    # Local imports: both modules import this one's helpers.
    from shopify_tool.packing_lists import sort_for_packing_list
    from shopify_tool.tag_manager import merge_tags

    # One row per order, carrying the order's total quantity.
    unique_orders = orders_df.groupby("Order_Number").first().reset_index()
    item_counts = orders_df.groupby("Order_Number")["Quantity"].sum().to_dict()
    unique_orders["item_count"] = unique_orders["Order_Number"].map(item_counts)

    # Merge tags from ALL rows of each order (not just the first row).
    # Internal_Tags is a serialized list (JSON string or native list), not
    # flat comma-separated text -- use tag_manager's parser/merger rather
    # than splitting the string ourselves, which corrupts multi-tag values
    # into something format_tags_for_barcode can't parse and leaks the raw
    # literal onto the printed label.
    if "Internal_Tags" in orders_df.columns:
        merged_tags = {
            order: merge_tags(group["Internal_Tags"].dropna().tolist())
            for order, group in orders_df.groupby("Order_Number", sort=False)
        }
        unique_orders["Internal_Tags"] = unique_orders["Order_Number"].map(merged_tags)

    # Label N is the N-th order on the packing list.
    unique_orders = sort_for_packing_list(unique_orders).reset_index(drop=True)

    results = generate_barcodes_batch(df=unique_orders)
    successful = [r for r in results if r["success"]]
    folder = Path(folder)
    outcome: dict[str, Any] = {
        "list": list_stem,
        "folder": str(folder),
        "labels": len(successful),
        "failed": len(results) - len(successful),
        "pdf": None,
        "qr_pdf": None,
        "qr_failed": False,
    }
    logger.info(
        f"Barcode generation for packing list {list_stem!r}: "
        f"{len(results)} orders filtered, "
        f"{outcome['labels']} labels written, {outcome['failed']} failed"
    )
    if not successful:
        return outcome

    if progress:
        progress(_writing(len(successful), "barcode"))
    outcome["pdf"] = str(
        generate_code128_labels_pdf(successful, barcode_pdf_path(folder, list_stem))
    )

    if qr:
        if progress:
            progress(_writing(len(successful), "QR"))
        try:
            outcome["qr_pdf"] = str(
                generate_qr_labels_pdf(successful, qr_pdf_path(folder, list_stem))
            )
        except Exception:
            logger.exception("QR labels PDF generation failed")
            outcome["qr_failed"] = True
    return outcome
