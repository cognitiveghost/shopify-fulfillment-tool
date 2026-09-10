"""ElidedLabel and row_widget: the two pieces that keep a Tools card from
being widened by its own content (spec §2, "Paths elide, they do not wrap")."""

from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QPushButton

from gui.components import ElidedLabel, row_widget

UNC_PATH = (
    "\\\\192.168.88.101\\_Fulfilment_\\Sessions\\" + "Client\\" * 30 + "labels.pdf"
)


def test_minimum_width_is_zero_even_for_a_path_with_no_spaces(qapp):
    label = ElidedLabel(UNC_PATH)
    assert label.minimumSizeHint().width() == 0


def test_a_long_path_elides_in_the_middle_and_keeps_the_full_text(qapp):
    label = ElidedLabel(UNC_PATH)
    label.resize(240, 24)
    label.show()
    QApplication.processEvents()

    assert label.text() != UNC_PATH
    assert "…" in label.text()
    assert label.text().startswith("\\\\")
    assert label.text().endswith("pdf")
    assert label.full_text() == UNC_PATH
    assert label.toolTip() == UNC_PATH


def test_short_text_is_shown_whole(qapp):
    label = ElidedLabel("No file chosen")
    label.resize(400, 24)
    label.show()
    QApplication.processEvents()
    assert label.text() == "No file chosen"


def test_set_text_replaces_the_full_text(qapp):
    label = ElidedLabel("first")
    label.setText("second")
    assert label.full_text() == "second"
    assert label.toolTip() == "second"


def test_row_widget_gives_the_named_widget_the_stretch(qapp):
    combo, button = QComboBox(), QPushButton("Refresh")
    row = row_widget(combo, button, stretch=combo)
    layout = row.layout()
    assert layout.count() == 2
    assert layout.stretch(0) == 1
    assert layout.stretch(1) == 0
    assert layout.contentsMargins().left() == 0


def test_row_widget_packs_left_when_nothing_stretches(qapp):
    row = row_widget(QCheckBox("a"), QCheckBox("b"))
    layout = row.layout()
    assert layout.count() == 3  # two widgets and a trailing stretch
    assert layout.itemAt(2).spacerItem() is not None
