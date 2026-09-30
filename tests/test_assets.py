"""The bundled asset pipeline: a glyph renders, and Inter registers."""
from pathlib import Path

import pytest

from shared.fonts import load_bundled_fonts
from shared.icons import glyph_url, icon


def test_icon_renders_a_pixmap(qapp):
    pixmap = icon("package").pixmap(16, 16)
    assert not pixmap.isNull()
    assert pixmap.width() == 16


def test_unknown_icon_name_raises(qapp):
    with pytest.raises(KeyError):
        icon("no-such-glyph")


def test_bundled_font_registers(qapp):
    assert load_bundled_fonts() == "Inter"


def _path_from_token(token: str) -> Path:
    assert token.startswith('url("') and token.endswith('")')
    return Path(token[len('url("'):-len('")')])


def test_glyph_url_writes_a_readable_png(qapp):
    path = _path_from_token(glyph_url("check"))
    assert path.is_file()
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_glyph_url_path_is_posix_spelled(qapp):
    assert "\\" not in glyph_url("check")


def test_glyph_url_colour_is_part_of_the_cache_key(qapp):
    red = glyph_url("check", color="#ff0000")
    blue = glyph_url("check", color="#0000ff")
    red_again = glyph_url("check", color="#ff0000")
    assert red != blue
    assert red == red_again


def test_glyph_url_unknown_name_raises(qapp):
    with pytest.raises(KeyError):
        glyph_url("no-such-glyph")
