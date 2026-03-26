"""
Barcode Generation History Manager.

Tracks all generated barcodes for audit and statistics.
History persisted per packing list in barcode_history.json.
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class BarcodeHistory:
    """Manager for barcode generation history."""

    def __init__(self, history_file: Path):
        """
        Initialize history manager.

        Args:
            history_file: Path to barcode_history.json
        """
        self.history_file = history_file
        self.data = self._load_history()

    def _load_history(self) -> Dict:
        """Load history from JSON file."""
        if not self.history_file.exists():
            logger.info(f"Creating new history file: {self.history_file}")
            self.history_file.parent.mkdir(parents=True, exist_ok=True)

            data = {"generated_barcodes": []}
            self._save_history(data)
            return data

        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            logger.info(f"Loaded history: {len(data.get('generated_barcodes', []))} entries")
            return data

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to load history: {e}")
            return {"generated_barcodes": []}

    def _save_history(self, data: Dict = None):
        """Save history to JSON file."""
        if data is None:
            data = self.data

        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Saved history: {len(data.get('generated_barcodes', []))} entries")

        except Exception as e:
            logger.error(f"Failed to save history: {e}")

    def add_entry(self, entry: Dict[str, Any]):
        """
        Add barcode generation entry to history.

        Args:
            entry: Entry dict from generate_barcode_label()
        """
        # Add timestamp if not present
        if 'generated_at' not in entry:
            entry['generated_at'] = datetime.now().isoformat()

        # Convert Path objects to strings for JSON serialization
        if 'file_path' in entry and entry['file_path'] is not None:
            entry['file_path'] = str(entry['file_path'])

        self.data['generated_barcodes'].append(entry)
        self._save_history()

        logger.info(f"Added history entry: {entry.get('order_number')}")

    def clear_history(self):
        """Clear all history entries."""
        self.data['generated_barcodes'] = []
        self._save_history()
        logger.info("History cleared")

    def get_statistics(self) -> Dict:
        """
        Get statistics from history.

        Returns:
            Dict with statistics:
                - total_barcodes: Total count
                - total_size_kb: Total file size
                - avg_size_kb: Average file size
                - courier_breakdown: Dict of courier counts
        """
        entries = self.data['generated_barcodes']

        if not entries:
            return {
                'total_barcodes': 0,
                'total_size_kb': 0,
                'avg_size_kb': 0,
                'courier_breakdown': {}
            }

        total_size = sum(e.get('file_size_kb', 0) for e in entries)

        # Courier breakdown
        courier_counts = {}
        for entry in entries:
            courier = entry.get('courier', 'Unknown')
            courier_counts[courier] = courier_counts.get(courier, 0) + 1

        return {
            'total_barcodes': len(entries),
            'total_size_kb': round(total_size, 1),
            'avg_size_kb': round(total_size / len(entries), 1),
            'courier_breakdown': courier_counts
        }
