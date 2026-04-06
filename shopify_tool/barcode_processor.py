"""
Barcode Label Generator for Warehouse Operations.

Generates Code-128 barcode labels optimized for Citizen CL-E300 thermal printer.
Label size: 68mm × 38mm @ 203 DPI

Label Layout (Split Design):
┌────────────────────────────────────────┐
│ #12│x5│DE│TAG │       |||||||||||     │  ← Info left, barcode right
│ ORDER-001234   │       |||||||||||     │
│ DHL 16/01/26   │       |||||||||||     │
└────────────────────────────────────────┘

Fields:
- Sequential number (#12)
- Item count (x5 = 5 items total)
- Country code (DE or N/A)
- Internal tag (URGENT, BOX, N/A)
- Order number (ORDER-001234)
- Courier (DHL, PostOne, DPD)
- Generation date (DD/MM/YY)
- Code-128 barcode
"""

import io
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
import json

import pandas as pd
import barcode
from barcode.codex import Code128
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import mm

logger = logging.getLogger(__name__)

# Monkey patch ImageWriter to disable text rendering and font loading
# This prevents "cannot open resource" errors when fonts are not available
def _noop_paint_text(self, *args, **kwargs):
    """No-op replacement for _paint_text to avoid font loading."""
    pass

ImageWriter._paint_text = _noop_paint_text


# === LABEL SPECIFICATIONS ===
# Optimized for Citizen CL-E300 thermal printer
DPI = 203
LABEL_WIDTH_MM = 68
LABEL_HEIGHT_MM = 38
LABEL_WIDTH_PX = int((LABEL_WIDTH_MM / 25.4) * DPI)   # 543px
LABEL_HEIGHT_PX = int((LABEL_HEIGHT_MM / 25.4) * DPI)  # 303px

# Layout zones (split design) - optimized for readability
INFO_SECTION_WIDTH = 200  # Left side for text info (compact but readable)
BARCODE_SECTION_WIDTH = LABEL_WIDTH_PX - INFO_SECTION_WIDTH  # Right side for barcode (343px, maximum space)
BARCODE_SECTION_X = INFO_SECTION_WIDTH  # X position where barcode starts

# Font sizes - reduced for long text support
FONT_SIZE_SMALL = 11   # For compact info line (#12 | x5 | DE | TAG)
FONT_SIZE_MEDIUM = 14  # For order number
FONT_SIZE_LARGE = 16   # For courier name (bold)


# === EXCEPTIONS ===
class BarcodeProcessorError(Exception):
    """Base exception for barcode processor."""
    pass


class InvalidOrderNumberError(BarcodeProcessorError):
    """Invalid order number for barcode encoding."""
    pass


class BarcodeGenerationError(BarcodeProcessorError):
    """Error during barcode generation."""
    pass


# === UTILITY FUNCTIONS ===

def sanitize_order_number(order_number: str) -> str:
    """
    Clean order number for Code-128 barcode encoding.

    Removes non-alphanumeric characters except hyphens and underscores.
    Code-128 supports alphanumeric content for reliable scanning.

    Args:
        order_number: Raw order number

    Returns:
        Sanitized order number safe for barcode

    Raises:
        InvalidOrderNumberError: If order number is empty after sanitization
    """
    if not order_number:
        raise InvalidOrderNumberError("Order number cannot be empty")

    # Remove non-alphanumeric except hyphen and underscore
    clean = ''.join(c for c in order_number if c.isalnum() or c in ['-', '_'])

    if not clean:
        raise InvalidOrderNumberError(f"Order number '{order_number}' contains no valid characters")

    return clean


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    Load font with fallback strategy.

    Tries to load Arial, falls back to DejaVu Sans if not available.

    Args:
        size: Font size in points
        bold: Whether to load bold variant

    Returns:
        PIL ImageFont object
    """
    font_name = "arialbd.ttf" if bold else "arial.ttf"

    try:
        # Try Windows fonts
        return ImageFont.truetype(font_name, size)
    except OSError:
        pass

    try:
        # Try system fonts (Linux/Mac)
        fallback = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        return ImageFont.truetype(fallback, size)
    except OSError:
        # Last resort: default font
        logger.warning(f"Could not load font {font_name}, using default")
        return ImageFont.load_default()


def format_tags_for_barcode(internal_tag: str) -> str:
    """
    Format internal tags for barcode label display.

    Parses JSON array format and returns all tags pipe-separated.

    Args:
        internal_tag: Internal tag string (JSON array format: '["GIFT+1", "GIFT+2"]')

    Returns:
        Formatted tag string with all tags pipe-separated

    Examples:
        >>> format_tags_for_barcode('["GIFT+1", "GIFT+2"]')
        "GIFT+1|GIFT+2"
        >>> format_tags_for_barcode("Priority")
        "Priority"
    """
    if not internal_tag or internal_tag == 'nan' or internal_tag == 'None':
        return ""

    # Try to parse as JSON array (Internal_Tags format)
    import json
    try:
        if internal_tag.startswith('[') and internal_tag.endswith(']'):
            tags_list = json.loads(internal_tag)
            if isinstance(tags_list, list) and tags_list:
                # Join all tags with pipe separator
                return '|'.join(str(tag).strip() for tag in tags_list if tag)
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: treat as plain string or pipe-separated
    if '|' in internal_tag:
        tags = [t.strip() for t in internal_tag.split('|') if t.strip()]
        return '|'.join(tags)

    return internal_tag.strip()


# === MAIN BARCODE GENERATION FUNCTIONS ===

def generate_barcode_label(
    order_number: str,
    sequential_num: int,
    courier: str,
    country: str,
    tag: str,
    item_count: int,
    output_dir: Path,
    label_width_mm: float = LABEL_WIDTH_MM,
    label_height_mm: float = LABEL_HEIGHT_MM
) -> Dict[str, Any]:
    """
    Generate single barcode label with complex layout.

    Creates 68x38mm label with:
    - Left section: Sequential#, item count, country, tag, order#, courier, date
    - Right section: Code-128 barcode

    Args:
        order_number: Order number (will be sanitized)
        sequential_num: Sequential order number (1, 2, 3, ...)
        courier: Courier name (DHL, PostOne, DPD, etc.)
        country: 2-letter country code (or empty)
        tag: Internal tag (or empty)
        item_count: Total quantity of items in order
        output_dir: Directory to save PNG file
        label_width_mm: Label width (default: 68mm)
        label_height_mm: Label height (default: 38mm)

    Returns:
        Dict with keys:
            - order_number: Original order number
            - sequential_num: Sequential number used
            - courier: Courier name
            - country: Country code (or "N/A")
            - tag: Tag used (or "N/A")
            - item_count: Item count
            - file_path: Path to generated PNG
            - file_size_kb: File size in KB
            - success: True if successful
            - error: Error message if failed (None if success)

    Raises:
        InvalidOrderNumberError: If order number invalid
        BarcodeGenerationError: If barcode generation fails
    """
    try:
        # === STEP 1: Sanitize and validate ===
        safe_order_number = sanitize_order_number(order_number)

        if not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)

        # Prepare display values
        country_display = country if country else "N/A"
        tag_display = format_tags_for_barcode(tag) if tag else "N/A"
        date_str = datetime.now().strftime("%d/%m/%y")

        # Calculate dimensions
        dpi = DPI
        label_width_px = int((label_width_mm / 25.4) * dpi)
        label_height_px = int((label_height_mm / 25.4) * dpi)

        # === STEP 2: Generate Code-128 barcode ===
        # Use Code128 class directly (new python-barcode API)
        barcode_class = Code128

        writer = ImageWriter()
        writer.set_options({
            'module_width': 0.35,    # Bar width (mm) - increased for better scanning
            'module_height': 20.0,   # Bar height (mm) - increased for taller barcode
            'dpi': dpi,
            'quiet_zone': 0,         # No quiet zone (we add manually)
            'write_text': False,     # We add text manually
            'text': '',              # Empty text to avoid font loading
            'font_size': 0,          # Zero font size to skip font initialization
        })

        barcode_instance = barcode_class(safe_order_number, writer=writer)

        # Generate barcode to BytesIO
        barcode_buffer = io.BytesIO()
        barcode_instance.write(barcode_buffer)
        barcode_buffer.seek(0)

        # Load barcode as PIL Image
        barcode_img = Image.open(barcode_buffer)

        # CRITICAL: Crop bottom part to remove text added by barcode library
        # Even with write_text=False, some versions add text anyway
        width, height = barcode_img.size
        # Crop bottom ~30% where text usually appears
        barcode_img = barcode_img.crop((0, 0, width, int(height * 0.75)))

        # === STEP 3: Create label canvas ===
        label_img = Image.new('RGB', (label_width_px, label_height_px), 'white')
        draw = ImageDraw.Draw(label_img)

        # Resize barcode to fit right section (MAXIMUM size)
        barcode_target_width = BARCODE_SECTION_WIDTH - 10  # Minimal margin
        barcode_target_height = label_height_px - 55       # Space for number below

        barcode_img_resized = barcode_img.resize(
            (barcode_target_width, barcode_target_height),
            Image.Resampling.LANCZOS
        )

        # Paste barcode on right side (centered horizontally, top aligned)
        barcode_x = BARCODE_SECTION_X + 5  # Minimal margin
        barcode_y = 5  # Minimal top margin
        label_img.paste(barcode_img_resized, (barcode_x, barcode_y))

        # === STEP 4: Add text info on left side ===
        # ALL fonts BOLD for better visibility
        font_small = load_font(18, bold=True)         # For labels (SUM, COU, TAG) - BOLD and bigger
        font_medium = load_font(24, bold=True)        # For values - BOLD and bigger
        font_header = load_font(26, bold=True)        # For seq# and date - BOLD and bigger
        font_courier = load_font(30, bold=True)       # For courier (bold) - even bigger
        font_barcode_num = load_font(36, bold=False)  # BIGGER font for barcode number (except last 3)
        font_barcode_num_bold = load_font(36, bold=True)  # BIGGER Bold font for last 3 digits
        font_tag_multiline = load_font(18, bold=True)  # BOLD font for multiline tags (increased from 16)

        left_margin = 6
        y_pos = 8  # Start from top

        # === TOP SECTION: Seq#, Courier, Date ===
        # Line 1: Sequential number (BOLD)
        draw.text((left_margin, y_pos), f"#{sequential_num}", font=font_header, fill='black')
        y_pos += 34

        # Line 2: Courier (BOLD, largest)
        courier_display = courier[:12] if len(courier) <= 12 else courier[:9] + "..."
        draw.text((left_margin, y_pos), courier_display, font=font_courier, fill='black')
        y_pos += 38

        # Line 3: Date (BOLD)
        draw.text((left_margin, y_pos), date_str, font=font_small, fill='black')
        y_pos += 26

        # === SEPARATOR LINE (thicker) ===
        line_y = y_pos
        draw.line([(left_margin, line_y), (INFO_SECTION_WIDTH - 6, line_y)], fill='black', width=3)
        y_pos += 16

        # === INFO SECTIONS (3 rows with labels and values, ALL BOLD) ===
        section_height = 36  # Height for each section (increased for bigger bold fonts)

        # Section 1: SUM (items count) - BOLD
        draw.text((left_margin, y_pos), "SUM:", font=font_small, fill='black')
        draw.text((left_margin + 65, y_pos), str(item_count), font=font_medium, fill='black')
        y_pos += section_height

        # Separator line (thicker)
        draw.line([(left_margin, y_pos - 8), (INFO_SECTION_WIDTH - 6, y_pos - 8)], fill='black', width=2)

        # Section 2: COU (country) - BOLD
        draw.text((left_margin, y_pos), "COU:", font=font_small, fill='black')
        draw.text((left_margin + 65, y_pos), country_display, font=font_medium, fill='black')
        y_pos += section_height

        # Separator line (thicker)
        draw.line([(left_margin, y_pos - 8), (INFO_SECTION_WIDTH - 6, y_pos - 8)], fill='black', width=2)

        # Section 3: TAG (internal tag) - MULTILINE, takes all remaining space
        draw.text((left_margin, y_pos), "TAG:", font=font_small, fill='black')

        # Calculate available space for tags (from current position to bottom of label)
        tag_start_y = y_pos
        available_height = label_height_px - tag_start_y - 6  # 6px bottom margin
        available_width = INFO_SECTION_WIDTH - left_margin - 65 - 6  # Space after "TAG:" label

        # Split tags by pipe and draw them in available space with wrapping
        if tag_display and tag_display != "N/A":
            tag_x = left_margin + 65
            tag_y = tag_start_y
            line_height = 22  # Line height for tag text (increased for bigger font)

            # Parse tags (can be pipe-separated like "GIFT+1|GIFT+2")
            tags = [t.strip() for t in tag_display.split('|') if t.strip()]

            # Draw tags with word wrapping
            current_line = ""
            for tag in tags:
                # Try to fit tag on current line
                test_line = current_line + (", " if current_line else "") + tag
                bbox = draw.textbbox((0, 0), test_line, font=font_tag_multiline)
                line_width = bbox[2] - bbox[0]

                if line_width <= available_width:
                    current_line = test_line
                else:
                    # Draw current line and start new line
                    if current_line:
                        draw.text((tag_x, tag_y), current_line, font=font_tag_multiline, fill='black')
                        tag_y += line_height
                    current_line = tag
                    # Truncate a single tag that is still wider than the available area
                    bbox_single = draw.textbbox((0, 0), current_line, font=font_tag_multiline)
                    if bbox_single[2] - bbox_single[0] > available_width:
                        for cut in range(len(current_line), 0, -1):
                            candidate = current_line[:cut] + "..."
                            if draw.textbbox((0, 0), candidate, font=font_tag_multiline)[2] <= available_width:
                                current_line = candidate
                                break
                        else:
                            current_line = "..."

                # Check if we're out of vertical space
                if tag_y + line_height > tag_start_y + available_height:
                    break

            # Draw last line
            if current_line and tag_y + line_height <= tag_start_y + available_height:
                draw.text((tag_x, tag_y), current_line, font=font_tag_multiline, fill='black')
        else:
            # No tags, just show N/A
            draw.text((left_margin + 65, tag_start_y), "N/A", font=font_tag_multiline, fill='black')

        # === Add order number below barcode (right side) - ONLY ONCE ===
        # Last 3 digits BOLD as requested
        barcode_num_text = safe_order_number

        # Split into first part and last 3 digits
        if len(barcode_num_text) > 3:
            first_part = barcode_num_text[:-3]
            last_three = barcode_num_text[-3:]
        else:
            first_part = ""
            last_three = barcode_num_text

        # Calculate widths for centering horizontally
        bbox_first = draw.textbbox((0, 0), first_part, font=font_barcode_num)
        bbox_last = draw.textbbox((0, 0), last_three, font=font_barcode_num_bold)
        width_first = bbox_first[2] - bbox_first[0]
        width_last = bbox_last[2] - bbox_last[0]
        total_width = width_first + width_last
        text_height = bbox_last[3] - bbox_last[1]  # Height of text

        # Center the combined text under barcode (both horizontally and vertically)
        # Calculate available space below barcode
        space_below_barcode = label_height_px - (barcode_y + barcode_target_height)
        # Center text vertically in available space (slightly above center for better look)
        text_y = barcode_y + barcode_target_height + (space_below_barcode - text_height) // 2 - 2
        text_x_start = barcode_x + (barcode_target_width - total_width) // 2

        # Draw ONLY if there's space (prevent duplicate)
        if text_y + 35 <= label_height_px:
            # Draw first part (regular)
            if first_part:
                draw.text((text_x_start, text_y), first_part, font=font_barcode_num, fill='black')

            # Draw last 3 digits (BOLD)
            text_x_last = text_x_start + width_first
            draw.text((text_x_last, text_y), last_three, font=font_barcode_num_bold, fill='black')

        # === STEP 5: Save PNG with DPI metadata ===
        output_file = output_dir / f"{safe_order_number}.png"
        label_img.save(output_file, dpi=(dpi, dpi))

        # Get file size
        file_size_kb = output_file.stat().st_size / 1024

        logger.info(f"Generated barcode label: {output_file}")

        return {
            "order_number": order_number,
            "sequential_num": sequential_num,
            "courier": courier,
            "country": country_display,
            "tag": tag_display,
            "item_count": item_count,
            "file_path": output_file,
            "file_size_kb": round(file_size_kb, 1),
            "success": True,
            "error": None
        }

    except InvalidOrderNumberError as e:
        logger.error(f"Invalid order number '{order_number}': {e}")
        return {
            "order_number": order_number,
            "sequential_num": 0,
            "courier": "",
            "country": "N/A",
            "tag": "N/A",
            "item_count": 0,
            "file_path": None,
            "file_size_kb": 0,
            "success": False,
            "error": str(e)
        }

    except Exception as e:
        logger.error(f"Failed to generate barcode for '{order_number}': {e}", exc_info=True)
        return {
            "order_number": order_number,
            "sequential_num": 0,
            "courier": "",
            "country": "N/A",
            "tag": "N/A",
            "item_count": 0,
            "file_path": None,
            "file_size_kb": 0,
            "success": False,
            "error": str(e)
        }


def generate_barcodes_batch(
    df: pd.DataFrame,
    output_dir: Path,
    sequential_map: Optional[Dict[str, int]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> List[Dict[str, Any]]:
    """
    Generate barcodes for multiple orders with progress tracking.

    Args:
        df: DataFrame with columns:
            - Order_Number (required)
            - Shipping_Provider (required, courier name)
            - Destination_Country (required, may be empty)
            - Internal_Tag (required, may be empty)
            - item_count (preferred) or Quantity (fallback): number of items in order
        output_dir: Directory to save PNG files
        sequential_map: Dict mapping Order_Number to sequential number (from sequential_order.json)
                       If None, will use row index + 1 as fallback
        progress_callback: Optional callback(current, total, message) for progress updates

    Returns:
        List of result dicts (one per order), same format as generate_barcode_label()

    Example:
        >>> from shopify_tool.sequential_order import load_sequential_order_map
        >>> sequential_map = load_sequential_order_map(session_path)
        >>> results = generate_barcodes_batch(
        ...     df=filtered_orders,
        ...     output_dir=Path("session/barcodes/DHL_Orders"),
        ...     sequential_map=sequential_map
        ... )
        >>> successful = sum(r['success'] for r in results)
        >>> print(f"Generated {successful}/{len(results)} barcodes")
    """
    results = []
    total_orders = len(df)

    logger.info(f"Starting batch barcode generation: {total_orders} orders")

    # Track if we're using independent numbering
    using_independent_numbering = sequential_map is None
    if using_independent_numbering:
        logger.info("Using independent packing list numbering (1, 2, 3...)")

    for idx, row in df.iterrows():
        # Get sequential number from map, or use packing list order (1, 2, 3...)
        order_number = str(row['Order_Number'])
        if sequential_map:
            sequential_num = sequential_map.get(order_number, idx + 1)
        else:
            # Independent numbering: each packing list starts from 1
            sequential_num = idx + 1

        # Progress callback
        if progress_callback:
            progress_callback(
                len(results) + 1,
                total_orders,
                f"Generating barcode {len(results) + 1} of {total_orders}..."
            )

        # Extract data from row
        order_number = str(row['Order_Number'])
        courier = str(row['Shipping_Provider'])

        # Handle country (may be NaN)
        country = str(row.get('Destination_Country', '')) if pd.notna(row.get('Destination_Country')) else ''

        # Handle Internal_Tag (check both 'Internal_Tag' and 'Internal_Tags' columns)
        tag_raw = row.get('Internal_Tags', row.get('Internal_Tag', ''))  # Try both column names
        tag = str(tag_raw) if pd.notna(tag_raw) and tag_raw else ''

        # Debug: log tag value
        if tag and tag != 'nan' and tag != 'None':
            logger.info(f"Order {order_number}: Tag found = '{tag}'")

        # Get item count (number of unique items/SKUs in order)
        # Use 'item_count' column if available, otherwise fall back to 'Quantity'
        item_count = int(row.get('item_count', row.get('Quantity', 1)))

        # Generate barcode
        try:
            result = generate_barcode_label(
                order_number=order_number,
                sequential_num=sequential_num,
                courier=courier,
                country=country,
                tag=tag,
                item_count=item_count,
                output_dir=output_dir
            )

            results.append(result)

        except Exception as e:
            logger.error(f"Failed to generate barcode for {order_number}: {e}", exc_info=True)

            results.append({
                "order_number": order_number,
                "sequential_num": 0,
                "courier": "",
                "country": "N/A",
                "tag": "N/A",
                "item_count": 0,
                "file_path": None,
                "file_size_kb": 0,
                "success": False,
                "error": str(e)
            })

    logger.info(
        f"Batch generation complete: {sum(r['success'] for r in results)}/{total_orders} successful"
    )

    return results


def generate_barcodes_pdf(
    barcode_files: List[Path],
    output_pdf: Path,
    label_width_mm: float = LABEL_WIDTH_MM,
    label_height_mm: float = LABEL_HEIGHT_MM
) -> Path:
    """
    Generate PDF from barcode PNG files.

    Creates a PDF with one barcode per page (68mm × 38mm pages).
    Optimized for direct printing on label stock.

    Args:
        barcode_files: List of PNG file paths to include
        output_pdf: Output PDF path
        label_width_mm: Label width (default: 68mm)
        label_height_mm: Label height (default: 38mm)

    Returns:
        Path to generated PDF

    Raises:
        ValueError: If barcode_files is empty
        BarcodeGenerationError: If PDF generation fails

    Example:
        >>> barcode_files = [
        ...     Path("barcodes/ORDER-001.png"),
        ...     Path("barcodes/ORDER-002.png")
        ... ]
        >>> pdf_path = generate_barcodes_pdf(
        ...     barcode_files,
        ...     Path("barcodes/DHL_Orders_barcodes.pdf")
        ... )
    """
    if not barcode_files:
        raise ValueError("Cannot generate PDF: no barcode files provided")

    try:
        # Create PDF with label-sized pages
        page_width = label_width_mm * mm
        page_height = label_height_mm * mm

        c = canvas.Canvas(str(output_pdf), pagesize=(page_width, page_height))

        for barcode_file in barcode_files:
            if not barcode_file.exists():
                logger.warning(f"Barcode file not found: {barcode_file}")
                continue

            # Draw barcode image to fill entire page (no margins)
            c.drawImage(
                str(barcode_file),
                0, 0,
                width=page_width,
                height=page_height,
                preserveAspectRatio=True
            )

            # Create new page for next barcode
            c.showPage()

        c.save()

        logger.info(f"Generated PDF: {output_pdf} ({len(barcode_files)} pages)")

        return output_pdf

    except Exception as e:
        raise BarcodeGenerationError(f"Failed to generate PDF: {e}") from e
