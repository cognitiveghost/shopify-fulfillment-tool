"""The app logos: one multi-size .ico per app, used for the window, the
taskbar and (via PyInstaller --icon) the exe itself."""
import pytest

from shared.icons import brand_icon


@pytest.mark.parametrize(
    "name, tile", [("fulfilment-tool", "#006fba"), ("packer-assistant", "#2c6630")]
)
def test_a_logo_carries_every_windows_size_and_its_tile_colour(qapp, name, tile):
    logo = brand_icon(name)
    assert {16, 32, 48, 256} <= {size.width() for size in logo.availableSizes()}
    # (4, 24) is inside the rounded tile and clear of the glyph.
    assert logo.pixmap(48, 48).toImage().pixelColor(4, 24).name() == tile


def test_an_unknown_logo_is_a_loud_error():
    with pytest.raises(KeyError):
        brand_icon("no-such-app")
