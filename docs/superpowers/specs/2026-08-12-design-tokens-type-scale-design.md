# Design Tokens & Type Scale — Design

Track 1 of the UI Design System Foundation epic
(`docs/superpowers/specs/2026-08-11-ui-design-system-vision-design.md`).
Todoist: `6hG88cVxxJHj27J3`.

## Problem

Font sizing in this app has no system. Verified against the code on 2026-08-12:

- **55 `font-size:` literals** across 10 files in `gui/`, at **12 distinct values**.
- They **mix units**: `9/10/11/12/14/16pt` *and* `10/11/13/14/16/20px`. Qt treats QSS
  `px` as device pixels, so the `px` sites — the Statistics-tab stat cards
  (`ui_manager.py:1603-1666`) and `report_selection_dialog.py` — do not scale with the
  Windows DPI setting while every `pt` site does. On a 150%-DPI machine those labels stay
  small while the rest of the UI grows. This is a defect, not just an inconsistency.
- **51 `font-weight: bold` literals**, only some of which coincide with a size.
- **8 `QFont`-based sites** (`setPointSize`/`setBold`), including one
  (`tag_delegate.py:53`) that builds `QFont()` from scratch and therefore drops the
  inherited font family.

Phase 6/7 carry five-plus "fresh look" tasks with nothing to redesign *into*. Every new
dialog currently picks a font size by eye.

`shared/theme.py` is synced one-way from `packing-tool` and must never be hand-edited here
(see `CLAUDE.md`). It contributes exactly one font size — `font-size: 10pt` on
`QPushButton` (`shared/theme.py:210`) — plus the `font_family` / `font_family_mono` tokens.
`ThemeTokens` is a `@dataclass(frozen=True)`, so `dataclasses.replace()` can override those
two fields but **cannot add new ones**. The type scale therefore lives locally in
`gui/theme_manager.py`, the repo-owned customization seam, exactly as the vision doc
specifies.

## The scale

A 1.20 modular ratio anchored on a 10pt body, rounded to integer point sizes. Qt's QSS
parser is unreliable on fractional `pt` values, so every step is a whole number.

| role | size | weight | intent |
|---|---|---|---|
| `caption` | 9pt | regular | hints, tips, feedback lines, secondary info, dense card labels |
| `body` | 10pt | regular | default text and button labels |
| `label` | 12pt | bold | emphasis, sub-headers, count badges, primary action buttons |
| `heading` | 14pt | bold | dialog and section headers |
| `display` | 17pt | bold | stat-card numbers — the visual anchor of the Statistics tab |

Geometric check from `body`: 10 → 12 → 14.4 ≈ 14 → 17.28 ≈ 17.

**One deliberate deviation.** The geometric step *below* body is 8.33pt. `caption` is 9pt
instead. This is a legibility floor: the app is used on a warehouse floor, and 20 of the
existing sites already sit at 9pt, so pinning the floor there regresses nothing. The ratio
governs from `body` upward, which is where the visual hierarchy actually lives.

**Five roles, not seven.** The scale deliberately does not carry a 12pt-regular or 16pt-bold
tier just to preserve the three one-off legacy values. A role that exists only to hold a
legacy size is a role the next developer picks by accident, which is the drift this epic
exists to stop.

## API

Two functions in `gui/theme_manager.py`, shaped to the two idioms already in the codebase.

```python
@dataclass(frozen=True)
class TypeStyle:
    size_pt: int
    bold: bool

TYPE_SCALE: dict[str, TypeStyle] = {
    "caption": TypeStyle(9, False),
    "body":    TypeStyle(10, False),
    "label":   TypeStyle(12, True),
    "heading": TypeStyle(14, True),
    "display": TypeStyle(17, True),
}

def font_css(role: str, bold: bool | None = None) -> str:
    """QSS fragment for f-string stylesheets: 'font-size: 12pt; font-weight: bold;'"""

def apply_font(target, role: str, bold: bool | None = None) -> None:
    """Set role sizing on anything exposing .font()/.setFont()."""
```

`font_css` serves the 55 stylesheet sites:

```python
info_label.setStyleSheet(f"color: {theme.text_secondary}; {font_css('caption')} padding: 10px;")
```

`apply_font` serves the 8 `QFont` sites. It is duck-typed on `.font()` / `.setFont()`,
which `QLabel`, `QListWidgetItem` and `QPainter` all satisfy — one helper, no per-type
overloads. Because it reads the target's *existing* font rather than constructing a fresh
`QFont()`, migrating `tag_delegate.py:53` also fixes that site's dropped font family.

The optional `bold=` override handles cases where the role is right but the weight differs —
notably the uppercase nav overline at `settings_window_pyside.py:250`
(`apply_font(header, "caption", bold=True)`). This is one parameter instead of bold/regular
twin roles for every tier.

`role` is looked up directly in `TYPE_SCALE`; an unknown role raises `KeyError` at the call
site. No silent fallback — a typo'd role must fail loudly during development rather than
render at a default size in production.

## Call-site mapping

Every site is migrated in this change. Sizes map **by role, not by nearest number** — that
is the point of a semantic scale.

| current | count | → role | note |
|---|---|---|---|
| `9pt` | 20 | `caption` | unchanged size |
| `10pt` | 7 | `body` | unchanged size |
| `11pt` bold | 10 | `label` | 11 → 12pt |
| `14pt` bold | 5 | `heading` | unchanged size |
| `12pt` (`client_card.py:152,155`) | 2 | `label` | 12 → 12pt. **Keep the weights distinct**: line 152 is the selected state, 155 the unselected one, and bold-vs-regular *is* that card's selection indicator. Selected → `font_css("label")`, unselected → `font_css("label", bold=False)` |
| `16pt` (`column_mapping_widget.py:152`) | 1 | `heading` | red required-field asterisk, 16 → 14pt |
| `20px` (stat/courier card numbers) | 2 | `display` | 15pt-equivalent → 17pt |
| `16px` (`barcode_generator_widget.py:251`) | 1 | `label` | hero "Generate" button, 12pt-equivalent → 12pt |
| `14px` (`ui_manager.py:1659`) | 1 | `label` | tag count badge, 10.5pt-equivalent → 12pt |
| `13px` (`report_selection_dialog.py:111,292`) | 2 | `body` + `bold=True` | button labels, 9.75pt-equivalent → 10pt |
| `11px` (`ui_manager.py:1630`) | 1 | `caption` | courier name, 8.25pt-equivalent → 9pt |
| `10px` (`ui_manager.py:1608,1634,1666`) | 3 | `caption` | dense card labels, 7.5pt-equivalent → 9pt |
| `QFont` 14pt bold (`client_sidebar.py:74`) | 1 | `heading` | unchanged size |
| `QFont` 8pt (`tag_delegate.py:53`) | 1 | `caption` | 8 → 9pt, also gains inherited family |
| `QFont` `pointSize()-1` bold (`settings_window_pyside.py:250`) | 1 | `caption` + `bold=True` | relative → absolute |

`font-weight: bold` declarations that carry **no** font size are left untouched. Only sites
that set a size are migrated.

**This sweep is not purely mechanical.** Before collapsing two sites onto one role, check
whether the weight difference between them encodes *state* rather than hierarchy — the
`client_card.py` pair above is exactly that case, and folding it into a single bold role
would silently delete the selection indicator. Where weight carries meaning, keep the role
and vary it with `bold=`.

### Layout risk

Checked: the stat / courier / tag cards (`ui_manager.py:1592-1670`) use `QVBoxLayout` with
`setMinimumWidth` and `setWordWrap` only — no fixed heights — and sit inside a scroll area.
Growing text makes those cards taller, not clipped. The Statistics tab will read visibly
chunkier; `tag_delegate` badges are measured against remaining cell width and degrade by
showing fewer badges. No layout breakage, but this is the change most worth eyeballing.

## Testing

New `tests/test_type_scale.py`. No GUI harness needed beyond the existing `conftest.py`
offscreen Qt fixture.

1. **Scale resolution** — each role resolves to its expected point size and weight;
   `font_css` emits the expected QSS fragment, with and without the `bold=` override; an
   unknown role raises `KeyError`.
2. **`apply_font` across target types** — a `QLabel`, a `QListWidgetItem` and a `QPainter`
   each receive the right point size and weight, and retain their original font family.
3. **Drift guard against `shared/theme.py`** — regex the `QPushButton` rule out of
   `build_stylesheet(get_theme("light"))` and assert its `font-size` still equals
   `TYPE_SCALE["body"].size_pt`. `shared/theme.py` is sync-owned by `packing-tool` and can
   change under this repo without warning; this fails loudly the moment it does.
4. **Bypass guard** — walk `gui/*.py` and assert zero remaining `font-size:` literals and
   zero `setPointSize` calls outside `gui/theme_manager.py`. This is what keeps the scale
   from rotting: a future dialog cannot hardcode a size without turning the suite red.

Guard 4 is absolute because the mapping table above covers every existing site — there is no
allowlist to maintain.

## Non-goals

- **No edits to `shared/theme.py`.** If the scale proves useful to `packing-tool` too, that
  is a future upstream change made there and synced back, per `CLAUDE.md`.
- **No QSS override block** injecting the scale into the global stylesheet so that
  `shared`'s `QPushButton` size comes from `TYPE_SCALE["body"]`. Both are 10pt today, and
  test 3 catches the moment they diverge. Add the mechanism when there is an actual
  divergence to resolve, not before.
- **No font-family change.** Embedding an open UI font and overriding `font_family` via
  `dataclasses.replace()` is Track 2. This track changes sizes only, against the existing
  `Segoe UI` default.
- **No spacing/color token work.** `ThemeTokens` already carries `spacing_*` and `radius`;
  the per-widget magic-number margins the vision doc mentions are Track 3's concern.
- **No new dependency, no new module.** The scale lives in the existing 99-line
  `gui/theme_manager.py`.

## Open question for the user

This is developed on Ubuntu; production is Windows 10/11 only. Sizes were chosen against
Qt's 96dpi point-to-pixel math, not observed on the target OS. The Statistics tab
(`display` 17pt, `caption` 9pt on cards previously at 20px/10px) is the surface most likely
to want a tweak after a real look. That tweak is a one-line edit to `TYPE_SCALE` — the whole
point of centralizing it — so it does not block merging.
