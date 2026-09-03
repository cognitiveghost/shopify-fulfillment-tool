# CONTEXT.md — domain glossary

The vocabulary this repo's specs, plans and code are all expected to use. One
canonical term per concept. A glossary only: no implementation detail, no
status, no roadmap.

See `docs/agents/domain.md` for how this file is maintained, and `docs/adr/`
for decisions.

---

## Rendering

**Qt tier** — the part of the UI drawn by PySide6 widgets and styled with QSS.
Everything except the two heavy views.

**Web tier** — the part drawn in a `QWebEngineView`, styled with real CSS.
Analysis Results and Info › Statistics only. See ADR 0001.

**Renderer** — either tier, when the point is that there are two of them and
one palette must serve both. Never used for `QSvgRenderer`; say
`QSvgRenderer` when that is what is meant.

## Assets

**Asset library** — `shared/assets/`, plus the two modules that read it
(`shared/icons.py`, `shared/fonts.py`). One library, both apps, both tiers.
Not `gui/assets/`, which it replaces, and not
`shopify_tool/templates/assets/`, which is fonts baked into *printed labels*
and is unrelated.

**Glyph** — one vendored Lucide drawing, named by its Lucide filename without
the extension (`trash-2`, `chevron-up`). The thing on disk.

**Icon** — a `QIcon` built from a glyph by `shared.icons.icon()`, recoloured
to a theme token. The thing a widget is given.

**Glyph URL** — a QSS `url("…")` token for a glyph, from
`shared.icons.glyph_url()`. The thing a stylesheet is given. See ADR 0002.

**Sub-control** — a part of a Qt widget that QSS addresses with `::` and that
Qt, not application code, draws: `QCheckBox::indicator`,
`QHeaderView::up-arrow`. Distinguished from a **delegate**, which application
code paints itself. Sub-controls can only take a glyph URL; delegates paint
paths directly and take neither.

## Theme

**Token** — one named field on `ThemeTokens` (`surface_sunken`, `text`,
`status_warning`). Names and roles are frozen; values are not.

**Alias** — a token that always carries another token's value
(`accent_green` ← `status_success`). Kept for legacy Qt-tier call sites; never
exported to the web tier.

**Plane** — a surface token used for elevation (`surface_sunken`,
`surface_overlay`, `surface_raised`, `surface`). Light nests downward, dark
upward, and that direction is frozen.

**Shim** — an app-local module that re-exports `shared/` under a name the app
already imported (`gui/theme_manager.py` here, `gui/theme.py` in
`packing-tool`). A shim adapts; it does not decide.

## Repos

**Canonical source** — `packing-tool`. Every `shared/` change is authored
there and arrives here through `scripts/sync_shared.py`, one-way. A `shared/`
file edited in this repo is overwritten by the next sync.
