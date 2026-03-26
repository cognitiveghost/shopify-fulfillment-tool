"""
PDF Processor for Reference Labels.

Processes courier label PDFs by:
1. Reading PDF and CSV mapping
2. Matching pages to reference numbers
3. Adding reference overlays
4. Sorting pages by reference number
5. Saving processed PDF
"""

import re
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Callable
import csv

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from io import BytesIO


logger = logging.getLogger(__name__)


# Custom Exceptions
class PDFProcessorError(Exception):
    """Base exception for PDF processor."""
    pass


class InvalidPDFError(PDFProcessorError):
    """Invalid or corrupted PDF file."""
    pass


class InvalidCSVError(PDFProcessorError):
    """Invalid CSV mapping file."""
    pass


class MappingError(PDFProcessorError):
    """Error matching pages to references."""
    pass


def process_reference_labels(
    pdf_path: str,
    csv_path: str,
    output_dir: str,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Dict:
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
        ref_order_map = create_reference_order_map(sorted_pages)

        for page_data in sorted_pages:
            page = page_data['page']
            ref = page_data['ref']

            if ref:
                ref_order_num = ref_order_map[ref]

                try:
                    # Add reference overlay
                    overlay = create_reference_overlay(
                        ref,
                        ref_order_num,
                        float(page.mediabox.width),
                        float(page.mediabox.height)
                    )
                    page.merge_page(PdfReader(overlay).pages[0])

                except Exception as e:
                    logger.error(f"Failed to add overlay for ref {ref}: {e}")

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
        logger.error(f"Unexpected error during PDF processing: {e}", exc_info=True)
        raise PDFProcessorError(f"Unexpected error: {e}")


def load_csv_mapping(csv_path: str) -> Dict[str, Dict]:
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

    # Try different encodings
    encodings = ['utf-8-sig', 'utf-8', 'cp1251', 'latin-1']

    for encoding in encodings:
        try:
            with open(csv_path, 'r', encoding=encoding, newline='') as f:
                reader = csv.reader(f)
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
                    logger.info(
                        f"CSV loaded with encoding {encoding}: {row_count} rows"
                    )
                    return mappings

        except UnicodeDecodeError:
            continue
        except Exception as e:
            logger.warning(f"Failed to read CSV with encoding {encoding}: {e}")
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


def match_reference(page_text: str, mapping: Dict) -> Optional[Dict]:
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


def extract_postone_number(text: str) -> Optional[str]:
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


def create_reference_order_map(sorted_pages: list) -> Dict[str, int]:
    """
    Create mapping of reference number to order position.

    Args:
        sorted_pages: List of sorted page data

    Returns:
        Dict: {ref_number: order_number}
    """
    ref_order_map = {}
    order_counter = 0
    last_ref = None

    for page_data in sorted_pages:
        ref = page_data['ref']
        if ref and ref != last_ref:
            order_counter += 1
            ref_order_map[ref] = order_counter
            last_ref = ref

    logger.debug(f"Created reference order map: {len(ref_order_map)} unique refs")

    return ref_order_map


def create_reference_overlay(
    reference_number: str,
    order_number: int,
    page_width: float,
    page_height: float
) -> BytesIO:
    """
    Create PDF overlay with reference number and order number.

    Format: "[order_number]. REF: [reference_number]"
    Position: Bottom left, 3 units from bottom

    Args:
        reference_number: Reference number to display
        order_number: Order number to display
        page_width: Page width in points
        page_height: Page height in points

    Returns:
        BytesIO: PDF overlay buffer
    """
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))

    # Fixed position for REF (never moves)
    x_ref = 200
    y_bottom = 3
    can.setFont("Helvetica-Bold", 10)

    # Draw REF text
    ref_text = f"REF: {reference_number}"
    can.drawString(x_ref, y_bottom, ref_text)

    # Calculate order number position (to the LEFT of REF)
    order_text = f"{order_number}."
    order_width = can.stringWidth(order_text, "Helvetica-Bold", 10)

    # Position order number to the left of REF (with 5 units spacing)
    x_order = x_ref - order_width - 5
    can.drawString(x_order, y_bottom, order_text)

    can.save()
    packet.seek(0)

    return packet


def generate_output_filename() -> str:
    """
    Generate output filename with timestamp.

    Returns:
        str: Filename like "labels_20250115_143022_processed.pdf"
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"labels_{timestamp}_processed.pdf"
