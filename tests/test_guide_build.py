"""Tests for shared/guide/build.py: Markdown to HTML to PDF for the user guides."""

from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage

from shared.guide.build import build_html, build_pdf
from shared.theme import LIGHT_THEME

GUIDE = "# Title\n\n## Part\n\n![Cap](img/en/a.png)\n"


def _write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    assert image.save(str(path))


@pytest.fixture
def guide(tmp_path):
    md = tmp_path / "guide.md"
    md.write_text(GUIDE, encoding="utf-8")
    _write_png(tmp_path / "img" / "en" / "a.png")
    return md


def test_build_pdf_writes_pdf(guide):
    out = build_pdf(guide)
    assert out == guide.with_suffix(".pdf")
    assert out.read_bytes().startswith(b"%PDF")


def test_missing_image_raises(guide):
    (guide.parent / "img" / "en" / "a.png").unlink()
    with pytest.raises(FileNotFoundError, match="img/en/a.png"):
        build_pdf(guide)


def test_html_uses_theme_colours(guide):
    html = build_html(guide)
    assert LIGHT_THEME.accent_fill in html
    assert LIGHT_THEME.text in html


def test_html_has_title_and_toc(guide):
    html = build_html(guide)
    assert "<title>Title</title>" in html
    assert 'class="toc"' in html
