"""A titled settings section: heading, optional description, form rows.

Deferred here from Track 3 so real call sites would shape the API -- see
docs/superpowers/specs/2026-08-12-component-library-design.md:12-17.

Replaces two patterns at once. QGroupBox + QFormLayout in the settings
pages, where the OS group-box chrome duplicates a title the nav already
shows; and the hand-rolled font_css("heading") label written three times
(sets.py, window.py's _ColumnConfigPage, mappings.py's instructions
paragraph). One component rather than a second PageHeader type.
"""

from PySide6.QtWidgets import QFormLayout, QFrame, QLabel, QVBoxLayout, QWidget

from gui.theme_manager import font_css, get_theme_manager


class FormSection(QFrame):
    """A titled block of form rows.

    Args:
        title: Section heading, rendered at the `label` type-scale role.
        description: Optional wrapped paragraph under the title, at
            `caption` in the secondary text colour. Omitted entirely when
            empty -- an empty QLabel still takes vertical space.
    """

    def __init__(
        self,
        title: str,
        description: str = "",
        *,
        label_width: int = 0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        theme = get_theme_manager().get_current_theme()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            theme.spacing_md, theme.spacing_sm, theme.spacing_md, theme.spacing_sm
        )
        layout.setSpacing(theme.spacing_xs)

        title_label = QLabel(title)
        title_label.setStyleSheet(font_css("label"))
        layout.addWidget(title_label)

        if description:
            desc_label = QLabel(description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet(
                f"color: {theme.text_secondary}; {font_css('caption')}"
            )
            layout.addWidget(desc_label)

        self.form = QFormLayout()
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setSpacing(theme.spacing_sm)
        # A pinned label column is what the setup card's "208px gutter" is:
        # QFormLayout already lays each row out as label + field, so fixing
        # the label's width and letting the field grow gives that geometry
        # without a second row idiom in the app.
        self._label_width = label_width
        if label_width:
            self.form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
            self.form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        layout.addLayout(self.form)

    def add_row(self, label: str, widget: QWidget, tooltip: str = "") -> QLabel:
        """Append a labelled row and return the label it built.

        The pages currently name a QLabel variable per row purely to hand it
        to addRow. The label is returned for the rare caller that needs a
        handle to it.

        `tooltip` is applied to the label as well as the widget, so hovering
        the row's text explains the field. A widget that already carries its
        own tooltip keeps it.
        """
        row_label = QLabel(label)
        if self._label_width:
            row_label.setFixedWidth(self._label_width)
        if tooltip:
            row_label.setToolTip(tooltip)
            if not widget.toolTip():
                widget.setToolTip(tooltip)
        self.form.addRow(row_label, widget)
        return row_label

    def add_widget(self, widget: QWidget) -> None:
        """Append a widget below the form rows.

        Not every section that wants a title holds form rows -- the courier
        mappings section is a title over a button-and-rows column.
        """
        self.layout().addWidget(widget)
