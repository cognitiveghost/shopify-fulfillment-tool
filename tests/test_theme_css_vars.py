"""theme_css_vars: the palette the web tier reads (ADR 0001, roadmap 9.11)."""

import re
from dataclasses import fields

import pytest

from shared.theme import (
    _ALIAS_PAIRS,
    _COLOR_FIELDS,
    DARK_THEME,
    DENSITY_PROFILES,
    LIGHT_THEME,
    TYPE_SCALE,
    get_density,
    set_density,
    theme_css_vars,
)

_DECL = re.compile(r"^  (--[a-z0-9-]+): ([^;{}]+);$")
_ALIASES = {alias for alias, _ in _ALIAS_PAIRS}


def _parse(css: str) -> dict[str, str]:
    lines = css.splitlines()
    assert lines[0] == ":root {" and lines[-1] == "}", css
    decls = {}
    for line in lines[1:-1]:
        m = _DECL.match(line)
        assert m, f"not a single clean declaration: {line!r}"
        assert m.group(1) not in decls, f"emitted twice: {m.group(1)}"
        decls[m.group(1)] = m.group(2)
    return decls


def _name(field_name: str) -> str:
    return "--" + field_name.replace("_", "-")


@pytest.fixture
def density():
    """Set a profile for one test and always put the previous one back."""
    before = get_density()
    yield set_density
    set_density(before)


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=lambda t: t.name)
def test_every_token_round_trips(theme, density):
    density("desk")
    decls = _parse(theme_css_vars(theme))
    for f in fields(theme):
        if f.name == "name" or f.name in _ALIASES:
            continue
        value = getattr(theme, f.name)
        expected = f"{value}px" if isinstance(value, int) else value
        assert decls[_name(f.name)] == expected, f.name


def test_every_colour_field_but_the_aliases_reaches_the_web_tier(density):
    density("desk")
    decls = _parse(theme_css_vars(LIGHT_THEME))
    for token in _COLOR_FIELDS:
        assert (_name(token) in decls) == (token not in _ALIASES), token


def test_one_mono_face_on_both_tiers(density):
    density("desk")
    decls = _parse(theme_css_vars(DARK_THEME))
    assert (
        decls["--font-family-mono"]
        == LIGHT_THEME.font_family_mono
        == "Consolas, monospace"
    )


@pytest.mark.parametrize("profile_name", ["desk", "floor"])
def test_type_and_density_are_the_active_profile(profile_name, density):
    density(profile_name)
    decls = _parse(theme_css_vars(LIGHT_THEME))
    profile = DENSITY_PROFILES[profile_name]
    assert decls["--control-height"] == f"{profile.control_height}px"
    assert decls["--row-height"] == f"{profile.row_height}px"
    assert decls["--padding-v"] == f"{profile.padding_v}px"
    assert decls["--padding-h"] == f"{profile.padding_h}px"
    assert "--type-overrides" not in decls
    for role, style in TYPE_SCALE.items():
        size = profile.type_overrides.get(role, style.size_pt)
        assert decls[_name(f"type_{role}_size")] == f"{size}pt", role
        assert decls[_name(f"type_{role}_weight")] == (
            "700" if style.bold else "400"
        ), role
