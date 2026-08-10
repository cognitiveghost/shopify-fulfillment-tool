"""
PDF Processor for Reference Labels.

Processes courier label PDFs by:
1. Reading PDF and CSV mapping
2. Matching pages to reference numbers
3. Adding reference overlays
4. Sorting pages by reference number
5. Saving processed PDF
"""

import csv
import logging
import re
import time
from collections.abc import Callable
from datetime import datetime
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.graphics.barcode import code128
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

_CONTENT_SCALE = 0.88


# Custom Exceptions
class PDFProcessorError(Exception):
    """Base exception for PDF processor."""


class InvalidPDFError(PDFProcessorError):
    """Invalid or corrupted PDF file."""


class InvalidCSVError(PDFProcessorError):
    """Invalid CSV mapping file."""


class MappingError(PDFProcessorError):
    """Error matching pages to references."""


def process_reference_labels(
    pdf_path: str,
    csv_path: str,
    output_dir: str,
    progress_callback: Callable[[int, int, str], None] | None = None
) -> dict:
    """
    Process PDF with reference labels.

    Args:
        pdf_path: Path to input PDF
        csv_path: Path to CSV mapping file
        output_dir: Output directory for processed PDF
        progress_callback: Optional callback(current, total, message)

    Returns:
        dict: {
            'output_file': str,
            'pages_processed': int,
            'matched': int,
            'unmatched': int,
            'processing_time': float
        }

    Raises:
        InvalidPDFError: If PDF is invalid or cannot be read
        InvalidCSVError: If CSV is invalid or has wrong format
        PDFProcessorError: For other processing errors
    """
    start_time = time.time()

    logger.info(f"Starting PDF processing: {pdf_path}")

    try:
        # Step 1: Load and validate PDF
        if progress_callback:
            progress_callback(0, 100, "Loading PDF...")

        try:
            reader = PdfReader(pdf_path)
            total_pages = len(reader.pages)

            if total_pages == 0:
                raise InvalidPDFError("PDF file has no pages")

            logger.info(f"PDF loaded: {total_pages} pages")

        except Exception as e:
            raise InvalidPDFError(f"Cannot read PDF: {e}")

        # Step 2: Load and validate CSV mapping
        if progress_callback:
            progress_callback(5, 100, "Loading CSV mapping...")

        try:
            mapping = load_csv_mapping(csv_path)

            if not mapping:
                raise InvalidCSVError("CSV file is empty or has no valid mappings")

            logger.info(f"CSV loaded: {len(mapping['by_postone'])} mappings")

        except PDFProcessorError:
            raise
        except Exception as e:
            raise InvalidCSVError(f"Cannot read CSV: {e}")

        # Step 3: Process pages and match references
        if progress_callback:
            progress_callback(10, 100, "Processing pages...")

        page_data_list = []
        matched = 0
        unmatched = 0

        for i, page in enumerate(reader.pages):
            # Update progress
            progress_pct = 10 + int((i / total_pages) * 70)
            if progress_callback:
                progress_callback(
                    progress_pct,
                    100,
                    f"Processing page {i+1}/{total_pages}"
                )

            # Extract page text
            try:
                page_text = page.extract_text()
            except Exception as e:
                logger.warning(f"Failed to extract text from page {i+1}: {e}")
                page_text = ""

            # Match reference
            ref_data = match_reference(page_text, mapping)

            if ref_data:
                matched += 1
                logger.debug(f"Page {i+1} matched: {ref_data['ref']}")
            else:
                unmatched += 1
                logger.debug(f"Page {i+1} not matched")

            # Store page data
            page_data_list.append({
                'page': page,
                'ref': ref_data['ref'] if ref_data else None,
                'original_order': i,
                'verified': ref_data['verified'] if ref_data else False
            })

        logger.info(f"Matching complete: {matched} matched, {unmatched} unmatched")

        # Step 4: Sort pages by reference number
        if progress_callback:
            progress_callback(80, 100, "Sorting pages...")

        sorted_pages = sort_pages_by_reference(page_data_list)

        # Step 5: Add reference overlays and save
        if progress_callback:
            progress_callback(85, 100, "Adding reference labels...")

        writer = PdfWriter()

        for page_data in sorted_pages:
            page = page_data['page']
            ref = page_data['ref']

            if ref:
                try:
                    # Courier PDFs set wildly different page /Rotate values (some
                    # ship pre-rotated 90/270 label stock instead of authoring
                    # content upright). Bake rotation into content first so
                    # mediabox always reflects the true visual page -- otherwise
                    # the "bottom" strip below lands on a different physical edge
                    # (top/left/right) depending on which courier produced the PDF.
                    page.transfer_rotation_to_content()

                    page_width = float(page.mediabox.width)
                    page_height = float(page.mediabox.height)

                    transform = Transformation().scale(_CONTENT_SCALE, _CONTENT_SCALE).translate(
                        tx=page_width * (1 - _CONTENT_SCALE) / 2,
                        ty=page_height * (1 - _CONTENT_SCALE),
                    )
                    page.add_transformation(transform)

                    overlay = create_reference_overlay(ref, page_width, page_height)
                    page.merge_page(PdfReader(overlay).pages[0])

                except Exception:
                    logger.exception(f"Failed to add overlay for ref {ref}")

            writer.add_page(page)

        # Step 6: Save output PDF
        if progress_callback:
            progress_callback(95, 100, "Saving PDF...")

        output_file = Path(output_dir) / generate_output_filename()

        with open(output_file, 'wb') as f:
            writer.write(f)

        processing_time = time.time() - start_time

        logger.info(
            f"PDF processing complete: {output_file} "
            f"({processing_time:.1f}s)"
        )

        if progress_callback:
            progress_callback(100, 100, "Complete!")

        return {
            'output_file': str(output_file),
            'pages_processed': total_pages,
            'matched': matched,
            'unmatched': unmatched,
            'processing_time': processing_time
        }

    except PDFProcessorError:
        # Re-raise our custom errors
        raise
    except Exception as e:
        # Catch all other errors
        logger.exception("Unexpected error during PDF processing")
        raise PDFProcessorError(f"Unexpected error: {e}")


def load_csv_mapping(csv_path: str) -> dict[str, dict]:
    """
    Load CSV mapping file.

    CSV Format (from Shipments-Green Delivery):
    Column 0: PostOne ID (R/P + 10 digits)
    Column 1: Tracking Number
    Column 2: Reference Number
    Column 6: Client Name

    Args:
        csv_path: Path to CSV file

    Returns:
        Dict with three mappings:
        {
            'by_postone': {postone_id: {ref, name}},
            'by_tracking': {tracking: {ref, name}},
            'by_name': {normalized_name: {ref, name}}
        }

    Raises:
        InvalidCSVError: If CSV cannot be read or is invalid
    """
    logger.debug(f"Loading CSV mapping: {csv_path}")

    mappings = {
        'by_postone': {},
        'by_tracking': {},
        'by_name': {}
    }

    # Read raw bytes once to avoid repeated network/disk I/O per encoding attempt
    try:
        raw_bytes = Path(csv_path).read_bytes()
    except OSError as e:
        raise InvalidCSVError(f"Could not read CSV file: {e}")

    encodings = ['utf-8-sig', 'utf-8', 'cp1251', 'latin-1']

    for encoding in encodings:
        try:
            text = raw_bytes.decode(encoding)
            reader = csv.reader(text.splitlines())
            header = next(reader, None)

            if not header:
                continue

            row_count = 0
            for row in reader:
                if len(row) < 7:
                    continue

                p_number = row[0].strip()
                tracking = row[1].strip()
                ref_num = row[2].strip()
                client_name = row[6].strip()

                data_pack = {'ref': ref_num, 'name': client_name}

                if p_number:
                    mappings['by_postone'][p_number] = data_pack
                if tracking:
                    mappings['by_tracking'][tracking] = data_pack
                if client_name:
                    normalized_name = normalize_text(client_name)
                    mappings['by_name'][normalized_name] = data_pack

                row_count += 1

            if row_count > 0:
                logger.info(f"CSV loaded with encoding {encoding}: {row_count} rows")
                return mappings

        except UnicodeDecodeError:
            continue
        except Exception as e:
            logger.warning(f"Failed to parse CSV with encoding {encoding}: {e}")
            continue

    raise InvalidCSVError("Could not read CSV file with any supported encoding")


def normalize_text(text: str) -> str:
    """
    Normalize text for comparison (remove extra spaces, lowercase).

    Args:
        text: Input text

    Returns:
        str: Normalized text
    """
    if not text:
        return ""
    return re.sub(r'\s+', ' ', str(text)).strip().lower()


def match_reference(page_text: str, mapping: dict) -> dict | None:
    """
    Match page text to reference using 3-step verification:
    1. PostOne ID (R/P + 10 digits)
    2. Tracking number
    3. Client name (fallback)

    Args:
        page_text: Extracted text from PDF page
        mapping: Mapping dictionary from load_csv_mapping()

    Returns:
        Dict with {'ref': str, 'verified': bool} or None if no match
    """
    # Step 1: Try PostOne ID
    postone_id = extract_postone_number(page_text)
    if postone_id and postone_id in mapping['by_postone']:
        data = mapping['by_postone'][postone_id]
        is_verified = check_name_presence(data['name'], page_text)

        logger.debug(
            f"Matched by PostOne ID: {postone_id} → {data['ref']} "
            f"(verified: {is_verified})"
        )

        return {
            'ref': data['ref'],
            'verified': is_verified,
            'method': 'postone'
        }

    # Step 2: Try Tracking Number
    tracking_nums = extract_tracking_numbers(page_text)
    for tracking in tracking_nums:
        if tracking in mapping['by_tracking']:
            data = mapping['by_tracking'][tracking]
            is_verified = check_name_presence(data['name'], page_text)

            logger.debug(
                f"Matched by Tracking: {tracking} → {data['ref']} "
                f"(verified: {is_verified})"
            )

            return {
                'ref': data['ref'],
                'verified': is_verified,
                'method': 'tracking'
            }

    # Step 3: Try Name Matching (fallback)
    page_text_norm = normalize_text(page_text)

    for name_key, data in mapping['by_name'].items():
        if len(name_key) > 5 and name_key in page_text_norm:
            is_verified = check_name_presence(data['name'], page_text)

            logger.debug(
                f"Matched by Name: {name_key} → {data['ref']} "
                f"(verified: {is_verified})"
            )

            return {
                'ref': data['ref'],
                'verified': is_verified,
                'method': 'name'
            }

    return None


def extract_postone_number(text: str) -> str | None:
    """
    Extract PostOne number (R or P + 10 digits) from text.

    Args:
        text: Input text

    Returns:
        str: PostOne number or None
    """
    try:
        match = re.search(r'[RP]\d{10}', text)
        return match.group(0) if match else None
    except Exception:
        return None


def extract_tracking_numbers(text: str) -> list:
    """
    Extract potential tracking numbers from text.

    Args:
        text: Input text

    Returns:
        list: List of tracking number strings
    """
    try:
        # Looking for long alphanumeric strings (common in tracking)
        # Excluding the R/P numbers
        matches = re.findall(r'(?<![RP])([A-Z0-9]{12,})', text)
        return matches if matches else []
    except Exception:
        return []


def check_name_presence(name: str, page_text: str) -> bool:
    """
    Check if parts of the name exist in the page text.

    Args:
        name: Full name to check
        page_text: Page text to search

    Returns:
        bool: True if significant part of name is found
    """
    if not name or not page_text:
        return False

    page_text_norm = normalize_text(page_text)

    # Split name into words (filter out short words)
    parts = [p.lower() for p in name.split() if len(p) > 2]

    if not parts:
        return False

    # Check if majority of name parts are in text
    matches = sum(1 for part in parts if part in page_text_norm)

    return matches >= (len(parts) / 2)


def sort_pages_by_reference(page_data_list: list) -> list:
    """
    Sort pages by reference number (numerical order).

    Args:
        page_data_list: List of page data dicts

    Returns:
        list: Sorted page data list (matched first, then unmatched)
    """
    # Separate matched and unmatched pages
    matched_pages = [p for p in page_data_list if p['ref'] is not None]
    unmatched_pages = [p for p in page_data_list if p['ref'] is None]

    # Sort matched pages by reference number
    def get_sort_key(page_data):
        try:
            ref_str = str(page_data['ref'])
            # Extract all digits
            numbers = re.findall(r'\d+', ref_str)
            if numbers:
                return (int(numbers[0]), ref_str, page_data['original_order'])
            else:
                # If no numbers, sort alphabetically
                return (float('inf'), ref_str, page_data['original_order'])
        except Exception:
            return (float('inf'), str(page_data['ref']), page_data['original_order'])

    matched_pages.sort(key=get_sort_key)

    logger.debug(
        f"Sorted {len(matched_pages)} matched pages, "
        f"{len(unmatched_pages)} unmatched pages"
    )

    # Return matched pages first, then unmatched
    return matched_pages + unmatched_pages


def create_reference_overlay(
    reference_number: str,
    page_width: float,
    page_height: float
) -> BytesIO:
    """
    Create PDF overlay with the Reference Number and a horizontal Code-128
    barcode encoding it, centered as one block in the bottom-middle of the
    strip freed up by process_reference_labels()'s content-shrink transform,
    with a separator line marking the strip off from the original content.

    Args:
        reference_number: Reference number to display and encode
        page_width: Page width in points
        page_height: Page height in points

    Returns:
        BytesIO: PDF overlay buffer
    """
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))

    strip_height = page_height * (1 - _CONTENT_SCALE)
    margin = 8

    # Separator: marks the boundary between the shrunk courier content above
    # and the added reference strip below, so the two are never mistaken for
    # one continuous original label.
    can.setLineWidth(0.75)
    can.line(margin, strip_height, page_width - margin, strip_height)

    can.setFont("Helvetica-Bold", 10)
    text = f"REF: {reference_number}"
    text_width = can.stringWidth(text, "Helvetica-Bold", 10)

    bar_height = strip_height * 0.6
    barcode = code128.Code128(reference_number, barHeight=bar_height, barWidth=0.8)

    gap = 12
    block_width = text_width + gap + barcode.width
    block_x = (page_width - block_width) / 2

    text_y = strip_height / 2 - 3
    can.drawString(block_x, text_y, text)
    barcode.drawOn(can, block_x + text_width + gap, (strip_height - bar_height) / 2)

    can.save()
    packet.seek(0)

    return packet


def generate_output_filename() -> str:
    """
    Generate output filename with timestamp.

    Returns:
        str: Filename like "labels_20250115_143022_processed.pdf"
    """
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    return f"labels_{timestamp}_processed.pdf"
