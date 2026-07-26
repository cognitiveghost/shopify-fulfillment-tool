"""
Reference Labels History Manager.

Manages processing history for reference labels in JSON format.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


logger = logging.getLogger(__name__)


class ReferenceLabelsHistory:
    """Manages processing history for reference labels."""

    HISTORY_FILENAME = "reference_labels_history.json"

    def __init__(self, session_dir: Path):
        """
        Initialize history manager.

        Args:
            session_dir: Session reference_labels directory
        """
        self.session_dir = Path(session_dir)
        self.history_file = self.session_dir / self.HISTORY_FILENAME

        self._ensure_directory()
        self._load_history()

    def _ensure_directory(self):
        """Ensure session directory exists."""
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def _load_history(self):
        """Load history from JSON file."""
        if not self.history_file.exists():
            self.data = {'processed_files': []}
            logger.debug("No history file found, starting fresh")
            return

        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                self.data = json.load(f)

            # Ensure structure exists
            if 'processed_files' not in self.data:
                self.data['processed_files'] = []

            logger.info(
                f"History loaded: {len(self.data['processed_files'])} entries"
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse history JSON: {e}", exc_info=True)
            # Create backup of corrupt file
            backup_file = self.history_file.with_suffix('.json.backup')
            self.history_file.rename(backup_file)
            logger.info(f"Corrupt history backed up to {backup_file}")

            # Start fresh
            self.data = {'processed_files': []}

        except Exception as e:
            logger.error(f"Failed to load history: {e}", exc_info=True)
            self.data = {'processed_files': []}

    def _save_history(self):
        """Save history to JSON file (atomic write)."""
        try:
            # Write to temp file first (atomic operation)
            temp_file = self.history_file.with_suffix('.json.tmp')

            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)

            # Rename (atomic on most filesystems)
            temp_file.replace(self.history_file)

            logger.debug(f"History saved: {len(self.data['processed_files'])} entries")

        except Exception as e:
            logger.error(f"Failed to save history: {e}", exc_info=True)
            raise

    def add_entry(
        self,
        input_pdf: str,
        input_csv: str,
        output_pdf: str,
        pages_processed: int,
        matched: int,
        unmatched: int,
        processing_time: float,
        status: str = 'success'
    ):
        """
        Add processing entry to history.

        Args:
            input_pdf: Input PDF filename
            input_csv: Input CSV filename
            output_pdf: Output PDF filename
            pages_processed: Total pages processed
            matched: Pages matched
            unmatched: Pages unmatched
            processing_time: Processing time in seconds
            status: Processing status (success/failed)
        """
        entry = {
            'processed_at': datetime.now().isoformat(),
            'input_pdf': input_pdf,
            'input_csv': input_csv,
            'output_pdf': output_pdf,
            'pages_processed': pages_processed,
            'matched': matched,
            'unmatched': unmatched,
            'processing_time': round(processing_time, 2),
            'status': status
        }

        self.data['processed_files'].append(entry)
        self._save_history()

        logger.info(f"Added history entry: {input_pdf} → {output_pdf}")

    def get_entries(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Get processing history entries.

        Args:
            limit: Optional limit on number of entries (newest first)

        Returns:
            List of entry dicts
        """
        entries = self.data['processed_files']

        # Sort by date (newest first)
        entries.sort(key=lambda x: x['processed_at'], reverse=True)

        if limit:
            return entries[:limit]

        return entries

    def clear(self):
        """Clear all history entries."""
        self.data['processed_files'] = []
        self._save_history()
        logger.info("History cleared")

    def get_statistics(self) -> Dict:
        """
        Get statistics from history.

        Returns:
            Dict with statistics
        """
        entries = self.data['processed_files']

        if not entries:
            return {
                'total_files': 0,
                'total_pages': 0,
                'total_matched': 0,
                'total_unmatched': 0,
                'avg_processing_time': 0,
                'success_rate': 0
            }

        total_pages = sum(e['pages_processed'] for e in entries)
        total_matched = sum(e['matched'] for e in entries)
        total_unmatched = sum(e['unmatched'] for e in entries)
        total_time = sum(e['processing_time'] for e in entries)
        success_count = sum(1 for e in entries if e.get('status') == 'success')

        return {
            'total_files': len(entries),
            'total_pages': total_pages,
            'total_matched': total_matched,
            'total_unmatched': total_unmatched,
            'avg_processing_time': round(total_time / len(entries), 2),
            'success_rate': round((success_count / len(entries)) * 100, 1)
        }
