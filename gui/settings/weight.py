"""Volumetric weight management: product dimensions and packaging boxes."""

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.settings.base import SettingsPage
from gui.theme_manager import font_css, get_theme_manager


class WeightPage(SettingsPage):
    """Volumetric weight config, stored under config_data["weight_config"]."""

    def __init__(self, weight_config: dict, column_mappings: dict, stock_csv_delimiter: str, parent=None):
        super().__init__(parent)
        self.column_mappings = column_mappings
        self.stock_csv_delimiter = stock_csv_delimiter

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(8, 8, 8, 8)

        theme = get_theme_manager().get_current_theme()

        weight_cfg = weight_config or {
            "volumetric_divisor": 6000,
            "products": {},
            "boxes": []
        }
        # Held by reference for collect() -- see SettingsPage's contract. Note
        # this is weight_cfg, not weight_config: an empty config substitutes a
        # fresh dict above, and that substitute is the one to keep.
        self._weight_config = weight_cfg

        # ---- Global Settings (compact row) ----
        global_row = QHBoxLayout()
        global_row.setContentsMargins(0, 0, 0, 0)
        div_label = QLabel("Volumetric Divisor (cm³ → kg):")
        self.weight_divisor_spin = QDoubleSpinBox()
        self.weight_divisor_spin.setRange(1, 100000)
        self.weight_divisor_spin.setDecimals(0)
        self.weight_divisor_spin.setValue(float(weight_cfg.get("volumetric_divisor", 6000)))
        self.weight_divisor_spin.setFixedWidth(100)
        self.weight_divisor_spin.setToolTip(
            "Volumetric weight formula: L × W × H / divisor\n"
            "6000 = DPD/Speedy standard (cm³ → kg)\n"
            "5000 = DHL/FedEx standard"
        )
        hint = QLabel("(6000 = DPD/Speedy · 5000 = DHL/FedEx)")
        hint.setStyleSheet(f"color: {theme.text_secondary}; {font_css('caption')}")
        global_row.addWidget(div_label)
        global_row.addWidget(self.weight_divisor_spin)
        global_row.addWidget(hint)
        global_row.addStretch()
        main_layout.addLayout(global_row)

        # ---- Sub-tabs: Products | Boxes ----
        weight_sub_tabs = QTabWidget()
        weight_sub_tabs.setDocumentMode(True)

        # --- Products sub-tab ---
        products_tab = QWidget()
        products_layout = QVBoxLayout(products_tab)
        products_layout.setContentsMargins(4, 6, 4, 4)
        products_layout.setSpacing(4)

        prod_toolbar = QHBoxLayout()
        import_sku_btn = QPushButton("Import from Stock CSV")
        import_sku_btn.setToolTip("Load SKUs from the current stock CSV file")
        import_sku_btn.clicked.connect(self._weight_import_skus_from_stock_csv)
        prod_toolbar.addWidget(import_sku_btn)
        import_dims_btn = QPushButton("Import Dimensions CSV")
        import_dims_btn.setToolTip("Import SKU dimensions from a CSV (columns: SKU, Name, L, W, H, No Packaging)")
        import_dims_btn.clicked.connect(self._weight_import_products_from_csv)
        prod_toolbar.addWidget(import_dims_btn)
        add_prod_btn = QPushButton("Add Row")
        add_prod_btn.clicked.connect(self._weight_add_product_row)
        prod_toolbar.addWidget(add_prod_btn)
        export_prod_btn = QPushButton("Export CSV")
        export_prod_btn.setToolTip("Export all products with dimensions to a CSV file")
        export_prod_btn.clicked.connect(self._weight_export_products_to_csv)
        prod_toolbar.addWidget(export_prod_btn)
        del_prod_btn = QPushButton("Delete Selected")
        del_prod_btn.clicked.connect(lambda: self._weight_delete_selected(self.weight_products_table))
        prod_toolbar.addWidget(del_prod_btn)
        prod_toolbar.addStretch()
        products_layout.addLayout(prod_toolbar)

        # ---- Quick Add (fast one-at-a-time entry) ----
        quick_add_box = QGroupBox("Quick Add")
        quick_add_row = QHBoxLayout(quick_add_box)
        quick_add_row.setContentsMargins(8, 4, 8, 4)

        self.weight_quick_sku = QLineEdit()
        self.weight_quick_sku.setPlaceholderText("SKU")
        self.weight_quick_sku.setMaximumWidth(140)
        quick_add_row.addWidget(self.weight_quick_sku)

        self.weight_quick_name = QLineEdit()
        self.weight_quick_name.setPlaceholderText("Name (optional)")
        quick_add_row.addWidget(self.weight_quick_name, 1)

        self.weight_quick_l = QDoubleSpinBox()
        self.weight_quick_w = QDoubleSpinBox()
        self.weight_quick_h = QDoubleSpinBox()
        for label_text, spin in (("L:", self.weight_quick_l), ("W:", self.weight_quick_w), ("H:", self.weight_quick_h)):
            quick_add_row.addWidget(QLabel(label_text))
            spin.setRange(0, 1000)
            spin.setDecimals(1)
            spin.setSuffix(" cm")
            spin.setMaximumWidth(90)
            quick_add_row.addWidget(spin)

        self.weight_quick_no_pkg = QCheckBox("No Packaging")
        quick_add_row.addWidget(self.weight_quick_no_pkg)

        quick_add_btn = QPushButton("Add")
        quick_add_btn.setToolTip("Add this SKU and keep the form open for the next one (Enter also works)")
        quick_add_btn.clicked.connect(self._weight_quick_add_product)
        quick_add_row.addWidget(quick_add_btn)

        self.weight_quick_sku.returnPressed.connect(self._weight_quick_add_product)
        self.weight_quick_name.returnPressed.connect(self._weight_quick_add_product)

        products_layout.addWidget(quick_add_box)

        self.products_search = QLineEdit()
        self.products_search.setPlaceholderText("Search by SKU or name...")
        self.products_search.setClearButtonEnabled(True)
        self.products_search.textChanged.connect(self._filter_products_table)
        products_layout.addWidget(self.products_search)

        self.weight_products_table = QTableWidget(0, 7)
        self.weight_products_table.setHorizontalHeaderLabels([
            "SKU", "Name", "L (cm)", "W (cm)", "H (cm)", "Vol. Weight (kg)", "No Packaging"
        ])
        self.weight_products_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.weight_products_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.weight_products_table.setColumnWidth(2, 70)
        self.weight_products_table.setColumnWidth(3, 70)
        self.weight_products_table.setColumnWidth(4, 70)
        self.weight_products_table.setColumnWidth(5, 110)
        self.weight_products_table.setColumnWidth(6, 100)
        self.weight_products_table.setAlternatingRowColors(True)
        self.weight_products_table.cellChanged.connect(
            lambda row, col: self._weight_recalc_vol_weight(self.weight_products_table, row, col, [2, 3, 4])
        )
        products_layout.addWidget(self.weight_products_table)

        weight_sub_tabs.addTab(products_tab, "Products (SKU Dimensions)")

        # --- Boxes sub-tab ---
        boxes_tab = QWidget()
        boxes_layout = QVBoxLayout(boxes_tab)
        boxes_layout.setContentsMargins(4, 6, 4, 4)
        boxes_layout.setSpacing(4)

        box_toolbar = QHBoxLayout()
        import_box_btn = QPushButton("Import CSV")
        import_box_btn.setToolTip("Import boxes from a CSV (columns: Name, L, W, H)")
        import_box_btn.clicked.connect(self._weight_import_boxes_from_csv)
        box_toolbar.addWidget(import_box_btn)
        add_box_btn = QPushButton("Add Box")
        add_box_btn.clicked.connect(self._weight_add_box_row)
        box_toolbar.addWidget(add_box_btn)
        export_box_btn = QPushButton("Export CSV")
        export_box_btn.setToolTip("Export all boxes to a CSV file")
        export_box_btn.clicked.connect(self._weight_export_boxes_to_csv)
        box_toolbar.addWidget(export_box_btn)
        del_box_btn = QPushButton("Delete Selected")
        del_box_btn.clicked.connect(lambda: self._weight_delete_selected(self.weight_boxes_table))
        box_toolbar.addWidget(del_box_btn)
        box_toolbar.addStretch()
        boxes_layout.addLayout(box_toolbar)

        self.boxes_search = QLineEdit()
        self.boxes_search.setPlaceholderText("Search by box name...")
        self.boxes_search.setClearButtonEnabled(True)
        self.boxes_search.textChanged.connect(self._filter_boxes_table)
        boxes_layout.addWidget(self.boxes_search)

        self.weight_boxes_table = QTableWidget(0, 5)
        self.weight_boxes_table.setHorizontalHeaderLabels([
            "Box Name", "L (cm)", "W (cm)", "H (cm)", "Vol. Weight (kg)"
        ])
        self.weight_boxes_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.weight_boxes_table.setColumnWidth(1, 70)
        self.weight_boxes_table.setColumnWidth(2, 70)
        self.weight_boxes_table.setColumnWidth(3, 70)
        self.weight_boxes_table.setColumnWidth(4, 110)
        self.weight_boxes_table.setAlternatingRowColors(True)
        self.weight_boxes_table.cellChanged.connect(
            lambda row, col: self._weight_recalc_vol_weight(self.weight_boxes_table, row, col, [1, 2, 3])
        )
        boxes_layout.addWidget(self.weight_boxes_table)

        tips_box = QLabel(
            "Volumetric weight = L × W × H / Divisor · "
            "No Packaging skips box selection · "
            "Values: box name / NO_BOX_NEEDED / NO_BOX_FITS / UNKNOWN_DIMS"
        )
        tips_box.setStyleSheet(f"color: {theme.text_secondary}; {font_css('caption')}")
        tips_box.setWordWrap(True)
        boxes_layout.addWidget(tips_box)

        weight_sub_tabs.addTab(boxes_tab, "Boxes (Packaging Reference)")

        main_layout.addWidget(weight_sub_tabs, 1)

        # Populate with existing data
        self._weight_populate_products(weight_cfg.get("products", {}))
        self._weight_populate_boxes(weight_cfg.get("boxes", []))

    def _weight_recalc_vol_weight(self, table, row, col, dim_cols):
        """Recalculate volumetric weight cell when L/W/H changes."""
        if col not in dim_cols:
            return
        vol_col = max(dim_cols) + 1
        try:
            l = float(table.item(row, dim_cols[0]).text() or 0) if table.item(row, dim_cols[0]) else 0
            w = float(table.item(row, dim_cols[1]).text() or 0) if table.item(row, dim_cols[1]) else 0
            h = float(table.item(row, dim_cols[2]).text() or 0) if table.item(row, dim_cols[2]) else 0
            divisor = float(self.weight_divisor_spin.value() or 6000)
            vol_w = round((l * w * h) / divisor, 4) if divisor > 0 else 0.0
            item = QTableWidgetItem(str(vol_w))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.blockSignals(True)
            table.setItem(row, vol_col, item)
            table.blockSignals(False)
        except (ValueError, AttributeError):
            pass

    def _weight_populate_products(self, products: dict):
        """Fill products table from config dict."""
        self.weight_products_table.blockSignals(True)
        self.weight_products_table.setRowCount(0)
        divisor = float(self.weight_divisor_spin.value() or 6000)
        for sku, data in products.items():
            row = self.weight_products_table.rowCount()
            self.weight_products_table.insertRow(row)
            l = float(data.get("length_cm") or 0)
            w = float(data.get("width_cm") or 0)
            h = float(data.get("height_cm") or 0)
            vol_w = round((l * w * h) / divisor, 4) if divisor > 0 else 0.0
            no_pkg = data.get("no_packaging", False)

            self.weight_products_table.setItem(row, 0, QTableWidgetItem(sku))
            self.weight_products_table.setItem(row, 1, QTableWidgetItem(data.get("name", "")))
            self.weight_products_table.setItem(row, 2, QTableWidgetItem(str(l) if l else ""))
            self.weight_products_table.setItem(row, 3, QTableWidgetItem(str(w) if w else ""))
            self.weight_products_table.setItem(row, 4, QTableWidgetItem(str(h) if h else ""))
            vol_item = QTableWidgetItem(str(vol_w))
            vol_item.setFlags(vol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.weight_products_table.setItem(row, 5, vol_item)

            # Checkbox for no_packaging
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.setContentsMargins(8, 2, 8, 2)
            chk = QCheckBox()
            chk.setChecked(bool(no_pkg))
            chk_layout.addWidget(chk)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.weight_products_table.setCellWidget(row, 6, chk_widget)
        self.weight_products_table.blockSignals(False)
        if hasattr(self, 'products_search'):
            self._filter_products_table(self.products_search.text())

    def _weight_populate_boxes(self, boxes: list):
        """Fill boxes table from config list."""
        self.weight_boxes_table.blockSignals(True)
        self.weight_boxes_table.setRowCount(0)
        divisor = float(self.weight_divisor_spin.value() or 6000)
        for box in boxes:
            row = self.weight_boxes_table.rowCount()
            self.weight_boxes_table.insertRow(row)
            l = float(box.get("length_cm") or 0)
            w = float(box.get("width_cm") or 0)
            h = float(box.get("height_cm") or 0)
            vol_w = round((l * w * h) / divisor, 4) if divisor > 0 else 0.0

            self.weight_boxes_table.setItem(row, 0, QTableWidgetItem(box.get("name", "")))
            self.weight_boxes_table.setItem(row, 1, QTableWidgetItem(str(l) if l else ""))
            self.weight_boxes_table.setItem(row, 2, QTableWidgetItem(str(w) if w else ""))
            self.weight_boxes_table.setItem(row, 3, QTableWidgetItem(str(h) if h else ""))
            vol_item = QTableWidgetItem(str(vol_w))
            vol_item.setFlags(vol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.weight_boxes_table.setItem(row, 4, vol_item)
        self.weight_boxes_table.blockSignals(False)
        if hasattr(self, 'boxes_search'):
            self._filter_boxes_table(self.boxes_search.text())

    def _filter_products_table(self, text: str):
        """Filter products table rows by SKU or name."""
        text = text.lower().strip()
        for row in range(self.weight_products_table.rowCount()):
            sku_item = self.weight_products_table.item(row, 0)
            name_item = self.weight_products_table.item(row, 1)
            sku_text = sku_item.text().lower() if sku_item else ""
            name_text = name_item.text().lower() if name_item else ""
            visible = not text or text in sku_text or text in name_text
            self.weight_products_table.setRowHidden(row, not visible)

    def _filter_boxes_table(self, text: str):
        """Filter boxes table rows by box name."""
        text = text.lower().strip()
        for row in range(self.weight_boxes_table.rowCount()):
            name_item = self.weight_boxes_table.item(row, 0)
            name_text = name_item.text().lower() if name_item else ""
            visible = not text or text in name_text
            self.weight_boxes_table.setRowHidden(row, not visible)

    def _weight_append_product_row(self, sku="", name="", l="", w="", h="", no_pkg=False):
        """Append one product row to the products table, filled with the given values."""
        divisor = float(self.weight_divisor_spin.value() or 6000)
        row = self.weight_products_table.rowCount()
        self.weight_products_table.insertRow(row)
        self.weight_products_table.setItem(row, 0, QTableWidgetItem(sku))
        self.weight_products_table.setItem(row, 1, QTableWidgetItem(name))
        self.weight_products_table.setItem(row, 2, QTableWidgetItem(str(l) if l else ""))
        self.weight_products_table.setItem(row, 3, QTableWidgetItem(str(w) if w else ""))
        self.weight_products_table.setItem(row, 4, QTableWidgetItem(str(h) if h else ""))
        try:
            vol_w = round((float(l or 0) * float(w or 0) * float(h or 0)) / divisor, 4) if divisor > 0 else 0.0
        except ValueError:
            vol_w = 0.0
        vol_item = QTableWidgetItem(str(vol_w))
        vol_item.setFlags(vol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.weight_products_table.setItem(row, 5, vol_item)
        chk_widget = QWidget()
        chk_layout = QHBoxLayout(chk_widget)
        chk_layout.setContentsMargins(8, 2, 8, 2)
        chk = QCheckBox()
        chk.setChecked(no_pkg)
        chk_layout.addWidget(chk)
        chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.weight_products_table.setCellWidget(row, 6, chk_widget)
        return row

    def _weight_add_product_row(self):
        """Add a blank product row to the products table."""
        self._weight_append_product_row()

    def _weight_quick_add_product(self):
        """Add one product from the Quick Add form and reset it for the next entry."""
        sku = self.weight_quick_sku.text().strip()
        if not sku:
            self.weight_quick_sku.setFocus()
            return

        existing_skus = {
            self.weight_products_table.item(r, 0).text().strip()
            for r in range(self.weight_products_table.rowCount())
            if self.weight_products_table.item(r, 0)
        }
        if sku in existing_skus:
            QMessageBox.warning(
                self, "Duplicate SKU",
                f"SKU '{sku}' is already in the table. Edit it there instead."
            )
            return

        self._weight_append_product_row(
            sku=sku,
            name=self.weight_quick_name.text().strip(),
            l=self.weight_quick_l.value(),
            w=self.weight_quick_w.value(),
            h=self.weight_quick_h.value(),
            no_pkg=self.weight_quick_no_pkg.isChecked(),
        )

        self.weight_quick_sku.clear()
        self.weight_quick_name.clear()
        self.weight_quick_l.setValue(0)
        self.weight_quick_w.setValue(0)
        self.weight_quick_h.setValue(0)
        self.weight_quick_no_pkg.setChecked(False)
        self.weight_quick_sku.setFocus()

    def _weight_add_box_row(self):
        """Add a blank box row to the boxes table."""
        row = self.weight_boxes_table.rowCount()
        self.weight_boxes_table.insertRow(row)
        for col in range(4):
            self.weight_boxes_table.setItem(row, col, QTableWidgetItem(""))
        vol_item = QTableWidgetItem("0.0")
        vol_item.setFlags(vol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.weight_boxes_table.setItem(row, 4, vol_item)

    def _weight_delete_selected(self, table):
        """Delete selected rows from the given table."""
        selected = sorted({idx.row() for idx in table.selectedIndexes()}, reverse=True)
        for row in selected:
            table.removeRow(row)

    def _weight_import_skus_from_stock_csv(self):
        """Import SKUs from a stock CSV file into the products table."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import SKUs from Stock CSV",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        try:
            df = pd.read_csv(file_path, sep=self.stock_csv_delimiter, dtype=str)

            # Find SKU and Name columns via column_mappings
            stock_mappings = (
                self.column_mappings.get("stock", {})
                if isinstance(self.column_mappings.get("stock"), dict)
                else {}
            )
            sku_col = next((csv_col for csv_col, internal in stock_mappings.items() if internal == "SKU"), None)
            name_col = next((csv_col for csv_col, internal in stock_mappings.items() if internal == "Product_Name"), None)

            if not sku_col or sku_col not in df.columns:
                # Fallback: try common names
                for candidate in ["SKU", "Артикул", "sku", "Article"]:
                    if candidate in df.columns:
                        sku_col = candidate
                        break

            if not sku_col:
                QMessageBox.warning(self, "Warning", "Could not find SKU column in CSV.\nCheck column mappings in Settings → Mappings tab.")
                return

            skus_in_csv = df[sku_col].dropna().astype(str).str.strip().unique().tolist()
            skus_in_csv = [s for s in skus_in_csv if s and s != "nan"]

            # Get existing SKUs in table
            existing_skus = set()
            for r in range(self.weight_products_table.rowCount()):
                item = self.weight_products_table.item(r, 0)
                if item:
                    existing_skus.add(item.text().strip())

            # Determine names if available
            sku_to_name = {}
            if name_col and name_col in df.columns:
                for _, row in df[[sku_col, name_col]].dropna(subset=[sku_col]).iterrows():
                    sku = str(row[sku_col]).strip()
                    name = str(row[name_col]).strip() if pd.notna(row[name_col]) else ""
                    if sku not in sku_to_name:
                        sku_to_name[sku] = name

            added = 0
            self.weight_products_table.blockSignals(True)
            for sku in skus_in_csv:
                if sku in existing_skus:
                    continue
                self._weight_append_product_row(sku=sku, name=sku_to_name.get(sku, ""))
                added += 1
            self.weight_products_table.blockSignals(False)

            QMessageBox.information(
                self, "Import Complete",
                f"Added {added} new SKUs. Skipped {len(skus_in_csv) - added} already existing."
            )

        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to import SKUs:\n\n{e!s}")

    def _weight_import_products_from_csv(self):
        """Import SKU dimensions from an arbitrary CSV into the products table."""
        from shopify_tool.csv_utils import detect_csv_delimiter

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Product Dimensions from CSV",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        try:
            delimiter, _ = detect_csv_delimiter(file_path)
            df = pd.read_csv(file_path, sep=delimiter, dtype=str)

            cols_lower = {c.lower().strip(): c for c in df.columns}

            def find_col(candidates):
                for c in candidates:
                    if c in cols_lower:
                        return cols_lower[c]
                return None

            sku_col = find_col(["sku", "артикул", "article", "код", "article_no"])
            name_col = find_col(["name", "назва", "product_name", "наименование", "title"])
            l_col = find_col(["l (cm)", "l(cm)", "length_cm", "length", "l", "довжина", "длина"])
            w_col = find_col(["w (cm)", "w(cm)", "width_cm", "width", "w", "ширина"])
            h_col = find_col(["h (cm)", "h(cm)", "height_cm", "height", "h", "висота", "высота"])
            np_col = find_col(["no_packaging", "no packaging", "без упаковки", "nopackaging"])

            if not sku_col:
                cols_str = ", ".join(df.columns.tolist())
                QMessageBox.warning(
                    self, "Column Not Found",
                    f"Could not find SKU column in CSV.\n\nAvailable columns: {cols_str}\n\n"
                    "Expected one of: SKU, Артикул, Article, Код"
                )
                return

            # Ask about duplicates
            existing_skus = {}
            for r in range(self.weight_products_table.rowCount()):
                item = self.weight_products_table.item(r, 0)
                if item:
                    existing_skus[item.text().strip()] = r

            rows_in_csv = df[sku_col].dropna().astype(str).str.strip().tolist()
            [s for s in rows_in_csv if s and s != "nan" and s not in existing_skus]
            dup_skus = [s for s in rows_in_csv if s and s != "nan" and s in existing_skus]

            update_existing = False
            if dup_skus:
                msg = QMessageBox(self)
                msg.setWindowTitle("Duplicates Found")
                msg.setText(f"Found {len(dup_skus)} SKU(s) already in the table.\nWhat would you like to do?")
                skip_btn = msg.addButton("Skip Duplicates", QMessageBox.ButtonRole.AcceptRole)
                update_btn = msg.addButton("Update Existing", QMessageBox.ButtonRole.ActionRole)
                msg.setDefaultButton(skip_btn)
                msg.exec()
                update_existing = msg.clickedButton() == update_btn

            divisor = float(self.weight_divisor_spin.value() or 6000)
            added = 0
            updated = 0
            skipped = 0

            def _val(row, col):
                if col and pd.notna(row.get(col)):
                    try:
                        return float(str(row[col]).replace(",", ".").strip())
                    except ValueError:
                        pass
                return None

            self.weight_products_table.blockSignals(True)
            for _, csv_row in df.iterrows():
                sku = str(csv_row[sku_col]).strip() if pd.notna(csv_row[sku_col]) else ""
                if not sku or sku == "nan":
                    continue

                name = str(csv_row[name_col]).strip() if name_col and pd.notna(csv_row.get(name_col)) else ""

                l = _val(csv_row, l_col)
                w = _val(csv_row, w_col)
                h = _val(csv_row, h_col)
                vol_w = round((l * w * h) / divisor, 4) if (l and w and h and divisor > 0) else 0.0

                no_pkg = False
                if np_col and pd.notna(csv_row.get(np_col)):
                    val = str(csv_row[np_col]).strip().lower()
                    no_pkg = val in ("true", "1", "yes", "так", "да")

                if sku in existing_skus:
                    if not update_existing:
                        skipped += 1
                        continue
                    row = existing_skus[sku]
                    if name_col:
                        self.weight_products_table.setItem(row, 1, QTableWidgetItem(name))
                    if l_col:
                        self.weight_products_table.setItem(row, 2, QTableWidgetItem(str(l) if l is not None else ""))
                    if w_col:
                        self.weight_products_table.setItem(row, 3, QTableWidgetItem(str(w) if w is not None else ""))
                    if h_col:
                        self.weight_products_table.setItem(row, 4, QTableWidgetItem(str(h) if h is not None else ""))
                    vol_item = QTableWidgetItem(str(vol_w))
                    vol_item.setFlags(vol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.weight_products_table.setItem(row, 5, vol_item)
                    chk_widget = self.weight_products_table.cellWidget(row, 6)
                    if chk_widget:
                        chk = chk_widget.findChild(QCheckBox)
                        if chk:
                            chk.setChecked(no_pkg)
                    updated += 1
                else:
                    self._weight_append_product_row(sku=sku, name=name, l=l, w=w, h=h, no_pkg=no_pkg)
                    added += 1
            self.weight_products_table.blockSignals(False)

            parts = [f"Added {added} new product(s)."]
            if updated:
                parts.append(f"Updated {updated} existing.")
            if skipped:
                parts.append(f"Skipped {skipped} duplicate(s).")
            QMessageBox.information(self, "Import Complete", " ".join(parts))

        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to import dimensions:\n\n{e!s}")

    def _weight_import_boxes_from_csv(self):
        """Import boxes from an arbitrary CSV into the boxes table."""
        from shopify_tool.csv_utils import detect_csv_delimiter

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Boxes from CSV",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        try:
            delimiter, _ = detect_csv_delimiter(file_path)
            df = pd.read_csv(file_path, sep=delimiter, dtype=str)

            cols_lower = {c.lower().strip(): c for c in df.columns}

            def find_col(candidates):
                for c in candidates:
                    if c in cols_lower:
                        return cols_lower[c]
                return None

            name_col = find_col(["box name", "box_name", "name", "назва", "size", "box", "коробка"])
            l_col = find_col(["l (cm)", "l(cm)", "length_cm", "length", "l", "довжина", "длина"])
            w_col = find_col(["w (cm)", "w(cm)", "width_cm", "width", "w", "ширина"])
            h_col = find_col(["h (cm)", "h(cm)", "height_cm", "height", "h", "висота", "высота"])

            if not name_col:
                cols_str = ", ".join(df.columns.tolist())
                QMessageBox.warning(
                    self, "Column Not Found",
                    f"Could not find box name column in CSV.\n\nAvailable columns: {cols_str}\n\n"
                    "Expected one of: Name, Box Name, Size, Box"
                )
                return

            existing_boxes = {}
            for r in range(self.weight_boxes_table.rowCount()):
                item = self.weight_boxes_table.item(r, 0)
                if item:
                    existing_boxes[item.text().strip()] = r

            dup_boxes = [
                str(r[name_col]).strip() for _, r in df.iterrows()
                if pd.notna(r.get(name_col)) and str(r[name_col]).strip() in existing_boxes
            ]

            update_existing = False
            if dup_boxes:
                msg = QMessageBox(self)
                msg.setWindowTitle("Duplicates Found")
                msg.setText(f"Found {len(dup_boxes)} box name(s) already in the table.\nWhat would you like to do?")
                skip_btn = msg.addButton("Skip Duplicates", QMessageBox.ButtonRole.AcceptRole)
                update_btn = msg.addButton("Update Existing", QMessageBox.ButtonRole.ActionRole)
                msg.setDefaultButton(skip_btn)
                msg.exec()
                update_existing = msg.clickedButton() == update_btn

            divisor = float(self.weight_divisor_spin.value() or 6000)
            added = 0
            updated = 0
            skipped = 0

            def _val(row, col):
                if col and pd.notna(row.get(col)):
                    try:
                        return float(str(row[col]).replace(",", ".").strip())
                    except ValueError:
                        pass
                return None

            self.weight_boxes_table.blockSignals(True)
            for _, csv_row in df.iterrows():
                name = str(csv_row[name_col]).strip() if pd.notna(csv_row[name_col]) else ""
                if not name or name == "nan":
                    continue

                l = _val(csv_row, l_col)
                w = _val(csv_row, w_col)
                h = _val(csv_row, h_col)
                vol_w = round((l * w * h) / divisor, 4) if (l and w and h and divisor > 0) else 0.0

                if name in existing_boxes:
                    if not update_existing:
                        skipped += 1
                        continue
                    row = existing_boxes[name]
                    if l_col:
                        self.weight_boxes_table.setItem(row, 1, QTableWidgetItem(str(l) if l is not None else ""))
                    if w_col:
                        self.weight_boxes_table.setItem(row, 2, QTableWidgetItem(str(w) if w is not None else ""))
                    if h_col:
                        self.weight_boxes_table.setItem(row, 3, QTableWidgetItem(str(h) if h is not None else ""))
                    vol_item = QTableWidgetItem(str(vol_w))
                    vol_item.setFlags(vol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.weight_boxes_table.setItem(row, 4, vol_item)
                    updated += 1
                else:
                    row = self.weight_boxes_table.rowCount()
                    self.weight_boxes_table.insertRow(row)
                    self.weight_boxes_table.setItem(row, 0, QTableWidgetItem(name))
                    self.weight_boxes_table.setItem(row, 1, QTableWidgetItem(str(l) if l is not None else ""))
                    self.weight_boxes_table.setItem(row, 2, QTableWidgetItem(str(w) if w is not None else ""))
                    self.weight_boxes_table.setItem(row, 3, QTableWidgetItem(str(h) if h is not None else ""))
                    vol_item = QTableWidgetItem(str(vol_w))
                    vol_item.setFlags(vol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.weight_boxes_table.setItem(row, 4, vol_item)
                    added += 1
            self.weight_boxes_table.blockSignals(False)

            parts = [f"Added {added} new box(es)."]
            if updated:
                parts.append(f"Updated {updated} existing.")
            if skipped:
                parts.append(f"Skipped {skipped} duplicate(s).")
            QMessageBox.information(self, "Import Complete", " ".join(parts))

        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to import boxes:\n\n{e!s}")

    def _weight_export_products_to_csv(self):
        """Export products table to a CSV file."""
        if self.weight_products_table.rowCount() == 0:
            QMessageBox.information(self, "Export", "No products to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Product Dimensions to CSV",
            "weight_products.csv",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        try:
            rows = []
            for r in range(self.weight_products_table.rowCount()):
                sku = self.weight_products_table.item(r, 0)
                name = self.weight_products_table.item(r, 1)
                l = self.weight_products_table.item(r, 2)
                w = self.weight_products_table.item(r, 3)
                h = self.weight_products_table.item(r, 4)
                chk_widget = self.weight_products_table.cellWidget(r, 6)
                no_pkg = False
                if chk_widget:
                    chk = chk_widget.findChild(QCheckBox)
                    if chk:
                        no_pkg = chk.isChecked()
                rows.append({
                    "SKU": sku.text().strip() if sku else "",
                    "Name": name.text().strip() if name else "",
                    "L (cm)": l.text().strip() if l else "",
                    "W (cm)": w.text().strip() if w else "",
                    "H (cm)": h.text().strip() if h else "",
                    "No Packaging": str(no_pkg),
                })
            df = pd.DataFrame(rows)
            df.to_csv(file_path, sep=";", index=False, encoding="utf-8-sig")
            QMessageBox.information(self, "Export Complete", f"Exported {len(rows)} product(s) to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export products:\n\n{e!s}")

    def _weight_export_boxes_to_csv(self):
        """Export boxes table to a CSV file."""
        if self.weight_boxes_table.rowCount() == 0:
            QMessageBox.information(self, "Export", "No boxes to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Boxes to CSV",
            "weight_boxes.csv",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        try:
            rows = []
            for r in range(self.weight_boxes_table.rowCount()):
                name = self.weight_boxes_table.item(r, 0)
                l = self.weight_boxes_table.item(r, 1)
                w = self.weight_boxes_table.item(r, 2)
                h = self.weight_boxes_table.item(r, 3)
                rows.append({
                    "Name": name.text().strip() if name else "",
                    "L (cm)": l.text().strip() if l else "",
                    "W (cm)": w.text().strip() if w else "",
                    "H (cm)": h.text().strip() if h else "",
                })
            df = pd.DataFrame(rows)
            df.to_csv(file_path, sep=";", index=False, encoding="utf-8-sig")
            QMessageBox.information(self, "Export Complete", f"Exported {len(rows)} box(es) to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export boxes:\n\n{e!s}")

    def collect(self) -> dict:
        """Collect weight configuration from UI tables."""
        divisor = int(self.weight_divisor_spin.value())

        products = {}
        for row in range(self.weight_products_table.rowCount()):
            sku_item = self.weight_products_table.item(row, 0)
            if not sku_item or not sku_item.text().strip():
                continue
            sku = sku_item.text().strip()
            name = (self.weight_products_table.item(row, 1) or QTableWidgetItem("")).text().strip()

            def _safe_float(table, r, c):
                item = table.item(r, c)
                if item and item.text().strip():
                    try:
                        return float(item.text().strip())
                    except ValueError:
                        pass
                return 0.0

            l = _safe_float(self.weight_products_table, row, 2)
            w = _safe_float(self.weight_products_table, row, 3)
            h = _safe_float(self.weight_products_table, row, 4)

            # Read checkbox
            no_pkg = False
            chk_widget = self.weight_products_table.cellWidget(row, 6)
            if chk_widget:
                chk = chk_widget.findChild(QCheckBox)
                if chk:
                    no_pkg = chk.isChecked()

            products[sku] = {
                "name": name,
                "length_cm": l,
                "width_cm": w,
                "height_cm": h,
                "no_packaging": no_pkg,
            }

        boxes = []
        for row in range(self.weight_boxes_table.rowCount()):
            name_item = self.weight_boxes_table.item(row, 0)
            if not name_item or not name_item.text().strip():
                continue
            name = name_item.text().strip()

            def _safe_float_b(r, c):
                item = self.weight_boxes_table.item(r, c)
                if item and item.text().strip():
                    try:
                        return float(item.text().strip())
                    except ValueError:
                        pass
                return 0.0

            boxes.append({
                "name": name,
                "length_cm": _safe_float_b(row, 1),
                "width_cm": _safe_float_b(row, 2),
                "height_cm": _safe_float_b(row, 3),
            })

        self._weight_config.update({
            "volumetric_divisor": divisor,
            "products": products,
            "boxes": boxes,
        })
        return {"weight_config": self._weight_config}
