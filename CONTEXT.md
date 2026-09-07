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

## Status and selection

**Channel** — one of the independent things a status says. **Colour** is the
role, **fill** is live-vs-resting, **mark** is person-vs-system, **shape** is
which state. One silhouette carries them. Supersedes the older rule where
tint carried authorship.

**Live** — a status someone still has to act on, drawn with the role's tint.
Its opposite is **resting**: terminal or waiting, drawn untinted. A property
of the state itself, not of the row.

**Mark** — the dot inside a status chip. Solid when a person set the status,
hollow when the system derived it. A painted disc or ring, never a character.
`StatusDot` is the mark; it is not a status form on its own.

**Shape** — the painted figure inside a session row's status cell, one per
state. Never a **glyph**, which is a vendored Lucide drawing, and never a
character. Where a screen shows eight states, shape replaces the **mark**:
authorship is constant per state and rides in the state table, so nothing is
lost by not drawing it.

**Chip** — the one status silhouette: an outlined pill carrying a mark and a
label. Distinguished from a **filter chip**, which is interactive and
dismissible, and from the **edge** variant, a lane marker that carries no
status of its own.

**Selection ring** — the closed rectangle around a selected table row. Its
horizontal sides come from QSS, its two end caps from a delegate, because
`QTableView::item` styles cells and a QSS left border would repeat at every
column boundary. Distinguished from the **status edge**, the 3px role-coloured
bar on the row's leftmost visible column, which insets inside the ring.

**State panel** — the widget a screen shows instead of its table when there
is nothing to show: nothing-loaded, working, no-results, or failed. Names the
cause, names the file or filter that caused it, and offers the action that
resolves it.

## Shell

**Shell** — the chrome around every screen: the rail, the command bar, the
page, and the status bar. Not a screen itself, and it never scrolls.

**Destination** — a place the rail navigates to and stays on. The rail holds
destinations and nothing else. Anything that *configures* an object is not a
destination, which is why the rail has no footer.

**Overflow** — the menu beside an object holding what configures it.
Qualified when the scope matters: the **command-bar overflow** holds what
configures the client and this PC; the **screen overflow** holds actions
scoped to the screen you are on. Two menus, two scopes, two bands of chrome.

**Connection state** — whether this PC can currently reach the file server.
One boolean, from `ProfileManager.is_network_available`, carried by one
signal. Every control that would touch the share is disabled from it; that
disabling is the guard, not a decoration on top of one.

## Session setup

**File slot** — the widget holding one of the two input files. One slot per
file, three states (empty, loaded, invalid), and the only thing that knows
whether its file is usable. Not a **file picker**, which is the dialog a slot
opens: the slot persists and changes state, the picker appears and closes.

**Strategy** — how a run allocates stock across competing orders, either
`multi-item-first` or `fifo`. Supersedes "analysis mode", which named the
combo rather than the thing it chose and collided with the Orders/Stock
"Load Mode" on the same screen.

## Sessions

**Blocked order** — an order this session cannot fulfil, counted as
`blocked_orders`. One number, one name: `SHORT ON STOCK` and `BLK` are both
retired. `not_fulfillable_orders` stays the persisted key, because it is a
file shared with another tool.

**Display status** — one of the eight states a session row shows, derived from
the four stored statuses plus packing progress and idle time. Distinguished
from **stored status**, the four values `SessionManager.VALID_STATUSES`
accepts and a person can set.

## Repos

**Canonical source** — `packing-tool`. Every `shared/` change is authored
there and arrives here through `scripts/sync_shared.py`, one-way. A `shared/`
file edited in this repo is overwritten by the next sync.
