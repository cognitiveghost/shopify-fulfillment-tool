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
            "tag": format_tags_for_barcode(tag) if tag else "N/A",
            "item_count": item_count,
            "success": True,
            "error": None
        })

    logger.info(
        f"Batch preparation complete: {sum(r['success'] for r in results)}/{total_orders} successful"
    )
    return results


# === PDF RENDERING ===

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
        orders: List of dicts: order_number (str), sku_qty_lines
            (list[tuple[str, int]] -- (SKU, quantity) pairs for that order).
        output_pdf: Output PDF path.

    Returns:
        Path to the generated PDF (same as output_pdf).

    Raises:
        ValueError: If orders is empty.
        BarcodeGenerationError: If rendering fails.
    """
    if not orders:
        raise ValueError("Cannot generate PDF: no orders provided")

    records = []
    for order in orders:
        lines = [f"{sku} x {qty}" for sku, qty in order["sku_qty_lines"]]
        qr_payload = "\n".join([order["order_number"], *lines])
        records.append({
            "order_number": order["order_number"],
            "qr_payload": qr_payload,
        })

    try:
        writer = LabelWriter(
            str(_QR_LABEL_TEMPLATE),
            default_stylesheets=(str(_FONTS_CSS), str(_QR_LABEL_STYLE)),
            items_per_page=1,
            label_tools=label_tools,
        )
        pdf_bytes = writer.write_labels(records, target="@memory")
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        output_pdf.write_bytes(pdf_bytes)
    except Exception as e:
        raise BarcodeGenerationError(f"Failed to generate QR labels PDF: {e}") from e

    logger.info(f"Generated QR labels PDF: {output_pdf} ({len(records)} pages)")
    return output_pdf
