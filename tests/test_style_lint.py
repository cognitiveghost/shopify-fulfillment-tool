"""Unit tests for the checker itself. The repo-wide guard lives in
tests/test_style_literals_guard.py; if that one fails these say why."""

import textwrap
from pathlib import Path

import pytest

from shared.style_lint import find_style_literals


def _scan(tmp_path: Path, source: str) -> list[str]:
    f = tmp_path / "sample.py"
    f.write_text(textwrap.dedent(source), encoding="utf-8")
    # Drop the path prefix: on Windows it carries a drive-letter colon, so
    # findings ("path:line: kind: text") cannot be split on ":" positionally.
    return [s.removeprefix(f"{f}:") for s in find_style_literals([f])]


def test_flags_six_digit_and_three_digit_hex(tmp_path):
    out = _scan(
        tmp_path,
        """
        LABEL = "color: #888888;"
        SHORT = "color: #888;"
    """,
    )
    assert len(out) == 2
    assert "#888888" in out[0] and "#888" in out[1]


def test_ignores_issue_numbers_in_comments(tmp_path):
    # The literal reason this is an ast checker and not a grep.
    assert (
        _scan(
            tmp_path,
            """
        # correct cleanup pattern learned from commit #216 failures
        X = 1
    """,
        )
        == []
    )


def test_ignores_order_numbers_in_docstrings(tmp_path):
    assert (
        _scan(
            tmp_path,
            '''
        def strip(order):
            """Normalise an order number: "#1001" -> "1001"."""
            return order
    ''',
        )
        == []
    )


def test_ignores_four_digit_run_that_merely_starts_like_a_hex(tmp_path):
    assert _scan(tmp_path, 'ORDER = "#1001"') == []


def test_flags_css_colour_keyword_only_in_a_declaration(tmp_path):
    out = _scan(
        tmp_path,
        """
        STYLE = "color: green; font-weight: bold;"
        PROSE = "Status: green means shipped"
    """,
    )
    assert len(out) == 1 and "green" in out[0]


def test_allows_transparent_and_qt_palette_roles(tmp_path):
    assert (
        _scan(
            tmp_path,
            """
        A = "border-left: 2px solid transparent;"
        B = "QFrame { border: 1px solid palette(mid); }"
    """,
        )
        == []
    )


def test_flags_pixel_font_sizes_but_not_points(tmp_path):
    out = _scan(
        tmp_path,
        """
        BAD = "font-size: 13px;"
        OK = "font-size: 10pt;"
    """,
    )
    assert len(out) == 1 and "px-font" in out[0]


def test_flags_reads_of_frozen_aliases(tmp_path):
    out = _scan(tmp_path, 'S = f"background: {theme.background_elevated};"')
    assert len(out) == 1 and "alias" in out[0]


def test_does_not_mistake_a_method_call_for_an_alias_read(tmp_path):
    # QPalette.background() is a call, not a token read.
    assert _scan(tmp_path, "c = widget.palette().background()") == []


def test_the_allow_marker_suppresses_one_line(tmp_path):
    assert _scan(tmp_path, 'DEFAULT_TAG = "#9E9E9E"  # style-lint: allow') == []


def test_f_string_fragments_are_scanned(tmp_path):
    out = _scan(tmp_path, 'S = f"color: {x}; background: #ffffff;"')
    assert len(out) == 1 and "#ffffff" in out[0]


def test_a_multiline_string_reports_the_line_the_literal_is_actually_on(tmp_path):
    findings = _scan(
        tmp_path,
        '''
        w.setStyleSheet("""
            QLabel { color: red; }
            QFrame { background: #123456; }
        """)
    ''',
    )
    assert [f.split(":")[0] for f in findings] == ["3", "4"]


def test_the_full_css_name_set_is_covered_not_just_the_common_dozen(tmp_path):
    findings = _scan(tmp_path, 'S = "color: forestgreen; background: whitesmoke;"')
    assert len(findings) == 2


def test_rgb_and_hsl_functions_pin_a_value_just_like_a_hex(tmp_path):
    findings = _scan(
        tmp_path, 'S = "color: rgba(1,2,3,0.5); border: 1px solid hsl(0,0%,0%)"'
    )
    assert len(findings) == 2 and all("css-func" in f for f in findings)


def test_the_font_shorthand_hides_a_pixel_size_too(tmp_path):
    assert _scan(tmp_path, "S = \"font: bold 13px 'Segoe UI'\"")


def test_a_colour_word_in_prose_is_still_not_a_finding(tmp_path):
    assert not _scan(tmp_path, 'S = "Tan leather and peru spice are in stock"')


# --- Web assets (ADR 0001, roadmap 9.11) ------------------------------------


def _scan_asset(tmp_path: Path, name: str, source: str) -> list[str]:
    f = tmp_path / name
    f.write_text(textwrap.dedent(source), encoding="utf-8")
    return [s.removeprefix(f"{f}:") for s in find_style_literals([f])]


def test_a_hex_in_a_stylesheet_is_flagged_on_its_own_line(tmp_path):
    out = _scan_asset(
        tmp_path,
        "page.css",
        """
        body { background: var(--surface); }
        .x { color: #ff0000; }
    """,
    )
    assert out == ["3: hex: #ff0000"]


def test_a_box_shadow_in_a_stylesheet_is_flagged(tmp_path):
    out = _scan_asset(
        tmp_path,
        "page.css",
        """
        .card { box-shadow: 0 1px 2px var(--border); }
    """,
    )
    assert out == ["2: banned: box-shadow"]


@pytest.mark.parametrize(
    "declaration, banned",
    [
        ("transition: color 0s;", "transition"),
        ("transition-duration: 1s;", "transition-duration"),
        ("transform: none;", "transform"),
        ("opacity: 0.5;", "opacity"),
        ("background-image: linear-gradient(var(--a), var(--b));", "linear-gradient"),
        (
            "background-image: repeating-radial-gradient(var(--a), var(--b));",
            "repeating-radial-gradient",
        ),
        ("background-image: conic-gradient(var(--a), var(--b));", "conic-gradient"),
    ],
)
def test_every_banned_property_is_flagged(tmp_path, declaration, banned):
    out = _scan_asset(tmp_path, "page.css", f".x {{ {declaration} }}\n")
    assert out == [f"1: banned: {banned}"]


def test_a_longer_property_merely_ending_in_a_banned_name_is_clean(tmp_path):
    assert (
        _scan_asset(
            tmp_path,
            "page.css",
            """
        .x { text-transform: uppercase; fill-opacity: 1; }
    """,
        )
        == []
    )


def test_a_pixel_font_size_in_a_stylesheet_is_flagged(tmp_path):
    out = _scan_asset(tmp_path, "page.css", "body { font-size: 13px; }\n")
    assert out == ["1: px-font: font-size: 13px"]


def test_comments_are_ignored_and_lines_still_count(tmp_path):
    out = _scan_asset(
        tmp_path,
        "page.css",
        """
        /* legacy #ffffff
           and a box-shadow: 0 0 1px */
        .x { color: #000; }
    """,
    )
    assert out == ["4: hex: #000"]


def test_html_style_blocks_are_scanned_but_comments_and_entities_are_not(tmp_path):
    out = _scan_asset(
        tmp_path,
        "page.html",
        """
        <!-- #ffffff -->
        <p>&#169; 2026</p>
        <style>.x { color: #abcdef; }</style>
    """,
    )
    assert out == ["4: hex: #abcdef"]


def test_a_script_is_scanned_without_mistaking_a_url_for_a_comment(tmp_path):
    out = _scan_asset(
        tmp_path,
        "page.js",
        """
        // #ffffff is only a comment
        const url = "qrc:///qtwebchannel/qwebchannel.js"; const c = "#abcdef";
        el.style.boxShadow = "none";
    """,
    )
    assert out == ["3: hex: #abcdef", "4: banned: boxShadow"]


def test_a_var_reading_a_frozen_alias_is_flagged(tmp_path):
    # Aliases without a colour word on purpose: var(--accent-blue) is ALSO a
    # css-name finding ("blue"), which is correct but would muddy this test.
    out = _scan_asset(
        tmp_path,
        "page.css",
        """
        .a { color: var(--active-border); }
        .b { background: var(--background-elevated, var(--surface)); }
        .c { background: var(--surface); }
    """,
    )
    assert out == ["2: alias: active-border", "3: alias: background-elevated"]


def test_the_allow_marker_works_in_a_web_asset(tmp_path):
    assert (
        _scan_asset(
            tmp_path,
            "page.css",
            """
        .x { color: #fff; } /* style-lint: allow */
    """,
        )
        == []
    )


def test_a_directory_walk_picks_up_web_assets_and_nothing_else(tmp_path):
    (tmp_path / "clean.py").write_text(
        'S = "color: palette(text);"\n', encoding="utf-8"
    )
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "page.css").write_text(
        ".x { color: #fff; }\n", encoding="utf-8"
    )
    (tmp_path / "notes.txt").write_text("color: #fff;\n", encoding="utf-8")
    out = find_style_literals([tmp_path])
    assert len(out) == 1 and out[0].startswith(str(tmp_path / "web" / "page.css"))


@pytest.mark.parametrize(
    "declaration, banned",
    [
        ("-webkit-box-shadow: none;", "-webkit-box-shadow"),
        ("-webkit-transition: color 1s;", "-webkit-transition"),
        ("-moz-transform: none;", "-moz-transform"),
        (
            "background-image: -webkit-linear-gradient(var(--a), var(--b));",
            "-webkit-linear-gradient",
        ),
        ("scale: 2;", "scale"),
        ("rotate: 45deg;", "rotate"),
        ("translate: 1em;", "translate"),
    ],
)
def test_a_vendor_prefix_or_an_individual_transform_is_still_banned(
    tmp_path, declaration, banned
):
    out = _scan_asset(tmp_path, "page.css", f".x {{ {declaration} }}\n")
    assert out == [f"1: banned: {banned}"]


@pytest.mark.parametrize(
    "statement, banned",
    [
        ("el.style.setProperty('box-shadow', 'none');", "box-shadow"),
        ('el.style.setProperty("-webkit-transform", "none");', "-webkit-transform"),
        ("el.style.webkitTransform = 'none';", "webkitTransform"),
        ("el.style.scale = '2';", "scale"),
    ],
)
def test_every_script_spelling_of_a_banned_property_is_flagged(
    tmp_path, statement, banned
):
    out = _scan_asset(tmp_path, "page.js", statement + "\n")
    assert out == [f"1: banned: {banned}"]
