"""
Client Reports Widget — Tab 6 content.

Shows global statistics per client in a sub-tab structure designed for
future expansion (additional report types can be added as new sub-tabs).

Current sub-tabs:
  - Label Printing: per-SKU label print counts with date range filtering and XLSX export
"""

import logging
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QDateEdit, QTableWidget, QTableWidgetItem,
    QSplitter, QHeaderView, QFileDialog, QMessageBox, QFrame,
    QGroupBox, QSizePolicy,
)
from PySide6.QtCore import Qt, QDate, QThreadPool

from gui.worker import Worker
from gui.theme_manager import get_theme_manager

logger = logging.getLogger(__name__)


def _compute_stats_from_history(history: list) -> dict:
    """Compute label stats from an already-filtered history list.

    Returns the same shape as StatsManager.get_label_stats() but without
    a second network round-trip.
    """
    sku_counts: dict[str, int] = {}
    for record in history:
        sku = record.get("sku", "Unknown")
        sku_counts[sku] = sku_counts.get(sku, 0) + record.get("copies", 1)
    total = sum(sku_counts.values())
    top_sku = max(sku_counts, key=sku_counts.get) if sku_counts else None
    return {
        "total_labels_printed": total,
        "unique_skus": len(sku_counts),
        "top_sku": top_sku,
        "sku_breakdown": sku_counts,
    }


class ClientReportsWidget(QWidget):
    """Tab 6 outer container — header + sub-tabs."""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.mw = main_window
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        theme = get_theme_manager().get_current_theme()

        self._header_label = QLabel("Reports")
        self._header_label.setStyleSheet(f"font-size: 13pt; font-weight: bold; color: {theme.text};")
        layout.addWidget(self._header_label)

        self._sub_tabs = QTabWidget()
        self._sub_tabs.setTabPosition(QTabWidget.North)

        self._label_tab = LabelPrintingTab(self.mw)
        self._sub_tabs.addTab(self._label_tab, "Label Printing")

        layout.addWidget(self._sub_tabs)

    def showEvent(self, event):
        super().showEvent(event)
        client_id = getattr(self.mw, "current_client_id", None)
        if client_id:
            self._header_label.setText(f"Reports — CLIENT_{client_id}")
        else:
            self._header_label.setText("Reports — No Client Selected")
        self._label_tab.refresh()


class _StatCard(QFrame):
    """Small summary card showing a value and a caption."""

    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        theme = get_theme_manager().get_current_theme()

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            f"QFrame {{ border: 1px solid {theme.border}; border-radius: 6px;"
            f" background-color: {theme.background}; padding: 6px; }}"
        )
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        self._value_label = QLabel("—")
        self._value_label.setAlignment(Qt.AlignCenter)
        self._value_label.setStyleSheet(f"font-size: 16pt; font-weight: bold; color: {theme.text};")
        layout.addWidget(self._value_label)

        caption_label = QLabel(caption)
        caption_label.setAlignment(Qt.AlignCenter)
        caption_label.setStyleSheet(f"color: {theme.text_secondary}; font-size: 9pt;")
        layout.addWidget(caption_label)

    def set_value(self, value: str):
        self._value_label.setText(value)


class LabelPrintingTab(QWidget):
    """Label Printing sub-tab — date filter, summary cards, tables, export."""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.mw = main_window
        self._history: list = []
        self._init_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self._create_filter_bar())
        layout.addWidget(self._create_summary_bar())
        layout.addWidget(self._create_tables_area(), 1)
        layout.addLayout(self._create_export_bar())

    def _create_filter_bar(self) -> QGroupBox:
        group = QGroupBox("Date Range")
        row = QHBoxLayout(group)
        row.setSpacing(8)

        theme = get_theme_manager().get_current_theme()

        row.addWidget(QLabel("From:"))
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDisplayFormat("dd/MM/yyyy")
        self._date_from.setDate(QDate.currentDate().addDays(-30))
        row.addWidget(self._date_from)

        row.addWidget(QLabel("To:"))
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDisplayFormat("dd/MM/yyyy")
        self._date_to.setDate(QDate.currentDate())
        row.addWidget(self._date_to)

        apply_btn = QPushButton("Apply")
        apply_btn.setMinimumWidth(70)
        apply_btn.clicked.connect(self.refresh)
        row.addWidget(apply_btn)

        reset_btn = QPushButton("Reset")
        reset_btn.setMinimumWidth(70)
        reset_btn.setStyleSheet(f"color: {theme.text_secondary};")
        reset_btn.clicked.connect(self._reset_dates)
        row.addWidget(reset_btn)

        row.addStretch()
        return group

    def _create_summary_bar(self) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        self._card_total = _StatCard("Total Labels Printed")
        self._card_skus = _StatCard("Unique SKUs")
        self._card_top = _StatCard("Top SKU")

        row.addWidget(self._card_total)
        row.addWidget(self._card_skus)
        row.addWidget(self._card_top)
        return container

    def _create_tables_area(self) -> QSplitter:
        splitter = QSplitter(Qt.Horizontal)

        # Left: SKU Breakdown
        left_group = QGroupBox("SKU Breakdown")
        left_layout = QVBoxLayout(left_group)
        left_layout.setContentsMargins(4, 4, 4, 4)

        self._breakdown_table = QTableWidget()
        self._breakdown_table.setColumnCount(2)
        self._breakdown_table.setHorizontalHeaderLabels(["SKU", "Total Copies"])
        self._breakdown_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._breakdown_table.setAlternatingRowColors(True)
        self._breakdown_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._breakdown_table.verticalHeader().setVisible(False)
        self._breakdown_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._breakdown_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        left_layout.addWidget(self._breakdown_table)

        # Right: Print History
        right_group = QGroupBox("Print History")
        right_layout = QVBoxLayout(right_group)
        right_layout.setContentsMargins(4, 4, 4, 4)

        self._history_table = QTableWidget()
        self._history_table.setColumnCount(3)
        self._history_table.setHorizontalHeaderLabels(["Timestamp", "SKU", "Copies"])
        self._history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._history_table.setAlternatingRowColors(True)
        self._history_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._history_table.verticalHeader().setVisible(False)
        self._history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        right_layout.addWidget(self._history_table)

        splitter.addWidget(left_group)
        splitter.addWidget(right_group)
        splitter.setSizes([350, 550])
        return splitter

    def _create_export_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch()
        export_btn = QPushButton("Export XLSX Report")
        export_btn.setMinimumWidth(160)
        export_btn.clicked.connect(self._on_export_clicked)
        row.addWidget(export_btn)
        return row

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self):
        client_id = getattr(self.mw, "current_client_id", None)
        base_path = (
            str(self.mw.profile_manager.base_path)
            if hasattr(self.mw, "profile_manager") and hasattr(self.mw.profile_manager, "base_path")
            else None
        )
        if not client_id or not base_path:
            self._show_no_client_state()
            return

        qdate_from = self._date_from.date()
        qdate_to = self._date_to.date()
        start_dt = datetime(qdate_from.year(), qdate_from.month(), qdate_from.day())
        end_dt = datetime(qdate_to.year(), qdate_to.month(), qdate_to.day())

        def _load():
            from shared.stats_manager import StatsManager
            mgr = StatsManager(base_path)
            history = mgr.get_label_print_history(
                client_id=client_id,
                start_date=start_dt,
                end_date=end_dt,
            )
            stats = _compute_stats_from_history(history)
            return history, stats

        worker = Worker(_load)
        worker.signals.result.connect(self._on_data_loaded)
        worker.signals.error.connect(
            lambda err: logger.error("Failed to load label stats: %s", err[1])
        )
        QThreadPool.globalInstance().start(worker)

    def _on_data_loaded(self, payload):
        history, stats = payload
        self._history = history
        self._populate_summary(stats)
        self._populate_breakdown(stats["sku_breakdown"])
        self._populate_history(history)

    # ------------------------------------------------------------------
    # Table/Card Population
    # ------------------------------------------------------------------

    def _populate_summary(self, stats: dict):
        self._card_total.set_value(str(stats["total_labels_printed"]))
        self._card_skus.set_value(str(stats["unique_skus"]))
        self._card_top.set_value(stats["top_sku"] or "—")

    def _populate_breakdown(self, sku_counts: dict):
        rows = sorted(sku_counts.items(), key=lambda x: -x[1])
        self._breakdown_table.setRowCount(len(rows))
        for row_idx, (sku, count) in enumerate(rows):
            sku_item = QTableWidgetItem(sku)
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._breakdown_table.setItem(row_idx, 0, sku_item)
            self._breakdown_table.setItem(row_idx, 1, count_item)

    def _populate_history(self, history: list):
        self._history_table.setRowCount(len(history))
        for row_idx, record in enumerate(history):
            try:
                ts = datetime.fromisoformat(record["timestamp"]).strftime("%Y-%m-%d %H:%M")
            except (KeyError, ValueError):
                ts = record.get("timestamp", "")
            ts_item = QTableWidgetItem(ts)
            sku_item = QTableWidgetItem(record.get("sku", ""))
            copies_item = QTableWidgetItem(str(record.get("copies", 0)))
            copies_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._history_table.setItem(row_idx, 0, ts_item)
            self._history_table.setItem(row_idx, 1, sku_item)
            self._history_table.setItem(row_idx, 2, copies_item)

    def _show_no_client_state(self):
        self._history = []
        self._populate_summary({"total_labels_printed": 0, "unique_skus": 0, "top_sku": None})
        self._breakdown_table.setRowCount(0)
        self._history_table.setRowCount(0)

    # ------------------------------------------------------------------
    # Date Reset
    # ------------------------------------------------------------------

    def _reset_dates(self):
        self._date_from.setDate(QDate.currentDate().addDays(-30))
        self._date_to.setDate(QDate.currentDate())
        self.refresh()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _on_export_clicked(self):
        client_id = getattr(self.mw, "current_client_id", None)
        if not client_id:
            QMessageBox.warning(self, "No Client", "Please select a client first.")
            return
        if not self._history:
            QMessageBox.information(
                self, "No Data",
                "No label print history for the selected date range."
            )
            return

        from datetime import date as _date
        default_name = f"label_report_{client_id}_{_date.today().isoformat()}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Label Report", default_name, "Excel Files (*.xlsx)"
        )
        if not file_path:
            return

        try:
            from openpyxl import Workbook

            wb = Workbook()
            stats = _compute_stats_from_history(self._history)

            # --- Sheet 1: Summary ---
            ws_summary = wb.active
            ws_summary.title = "Summary"
            ws_summary.append(["Metric", "Value"])
            ws_summary.append(["Client", f"CLIENT_{client_id}"])
            ws_summary.append(["Date From", self._date_from.date().toString("yyyy-MM-dd")])
            ws_summary.append(["Date To", self._date_to.date().toString("yyyy-MM-dd")])
            ws_summary.append(["Total Labels Printed", stats["total_labels_printed"]])
            ws_summary.append(["Unique SKUs", stats["unique_skus"]])
            ws_summary.append(["Top SKU", stats["top_sku"] or "—"])
            ws_summary.append([])
            ws_summary.append(["SKU Breakdown", ""])
            ws_summary.append(["SKU", "Total Copies"])
            for sku, count in sorted(stats["sku_breakdown"].items(), key=lambda x: -x[1]):
                ws_summary.append([sku, count])

            # --- Sheet 2: History ---
            ws_history = wb.create_sheet("History")
            ws_history.append(["Timestamp", "SKU", "Copies"])
            for record in self._history:
                ws_history.append([
                    record.get("timestamp", ""),
                    record.get("sku", ""),
                    record.get("copies", 0),
                ])

            wb.save(file_path)
            QMessageBox.information(
                self, "Export Complete",
                f"Report saved to:\n{file_path}"
            )
        except Exception as exc:
            logger.exception("Label report export failed")
            QMessageBox.critical(self, "Export Error", f"Failed to export report:\n{exc}")
