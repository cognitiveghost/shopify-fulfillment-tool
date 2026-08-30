"""The rail is 56px wide, so its labels have to actually fit in 56px.

8.6 shipped the five former tab titles verbatim onto a 56px rail and Qt
elided every one of them: "Session Setup" rendered as "Ses...tup", "Analysis
Results" as "Anal...ults", "Session Browser" as "Ses...ser". A middle-elided
label is worse than no label -- it costs a row of pixels and reads as noise.

No existing test caught it because nothing measured a rendered string against
the width it has to fit into.
"""
import pytest
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication

from gui.icons import icon
from gui.ui_manager import UIManager
from shared.navrail import RAIL_WIDTH, NavRail


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# QToolButton keeps a few px of padding either side of the label.
TEXT_BUDGET = RAIL_WIDTH - 8

# The "Sans Serif" alias resolves to whatever font is installed on the box
# running the test -- Noto Sans on this dev machine, DejaVu Sans on the CI
# runner -- so measuring it made the test's result depend on which fonts a
# given Linux machine happens to have, not on the label. Pin a specific,
# widely-available font so every machine measures the same thing, and add a
# little headroom on top since it's still a Linux proxy for the Inter/Segoe UI
# the production Windows build actually resolves.
MEASURING_FONT = "DejaVu Sans"
HEADROOM = 0.05


@pytest.fixture
def metrics(qapp):
    rail = NavRail()
    font = rail.button(rail.add_item(icon("clipboard-list"), "x")).font()
    font.setFamily(MEASURING_FONT)
    return QFontMetrics(font)


@pytest.mark.parametrize("label", [*UIManager._RAIL_LABELS, "Server"])
def test_every_rail_label_fits_without_eliding(metrics, label):
    width = metrics.horizontalAdvance(label)
    assert width <= TEXT_BUDGET * (1 - HEADROOM), (
        f"{label!r} is {width}px; the 56px rail gives it "
        f"{TEXT_BUDGET}px and Qt will elide it to a '...' form"
    )


def test_the_rail_has_one_label_per_destination():
    assert len(UIManager._RAIL_LABELS) == len(UIManager._TAB_LABELS)
