"""Tests for shared/guide/build.py: Markdown to HTML to PDF for the user guides."""

import re
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage

from shared.guide.build import build_html, build_pdf
from shared.theme import LIGHT_THEME

GUIDE = "# Title\n\n## Part\n\n![Cap](img/en/a.png)\n"
USER_GUIDE_DIR = Path(__file__).resolve().parents[1] / "docs" / "user-guide"
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


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


def test_fulfilment_guide_images_exist():
    assert (USER_GUIDE_DIR / "en.md").is_file()
    for guide in (USER_GUIDE_DIR / "en.md", USER_GUIDE_DIR / "bg.md"):
        if not guide.is_file():
            continue
        for src in _IMAGE_RE.findall(guide.read_text(encoding="utf-8")):
            assert (USER_GUIDE_DIR / src).is_file(), f"{guide.name} points at missing {src}"


def test_fulfilment_guide_uses_every_screenshot():
    text = (USER_GUIDE_DIR / "en.md").read_text(encoding="utf-8")
    shots = {path.name for path in (USER_GUIDE_DIR / "img" / "en").glob("*.png")}
    used = {Path(src).name for src in _IMAGE_RE.findall(text)}
    assert shots - used == set()


def test_fulfilment_guide_bg_matches_en():
    en = (USER_GUIDE_DIR / "en.md").read_text(encoding="utf-8")
    bg_path = USER_GUIDE_DIR / "bg.md"
    assert bg_path.is_file()
    bg = bg_path.read_text(encoding="utf-8")
    en_srcs = _IMAGE_RE.findall(en)
    bg_srcs = _IMAGE_RE.findall(bg)
    assert [Path(src).name for src in bg_srcs] == [Path(src).name for src in en_srcs]
    assert all(src.startswith("img/bg/") for src in bg_srcs)
    assert all(src.startswith("img/en/") for src in en_srcs)
    for prefix in ("## ", "### "):
        en_count = sum(line.startswith(prefix) for line in en.splitlines())
        bg_count = sum(line.startswith(prefix) for line in bg.splitlines())
        assert bg_count == en_count, f"{prefix!r} headings: bg {bg_count} vs en {en_count}"
