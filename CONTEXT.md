# CONTEXT.md — domain glossary

The vocabulary this repo's specs, plans and code are all expected to use. One
canonical term per concept. A glossary only: no implementation detail, no
status, no roadmap.

See `docs/agents/domain.md` for how this file is maintained, and `docs/adr/`
for decisions.

---

## Rendering

**Qt tier** — the part of the UI drawn by PySide6 widgets and styled with QSS.
Everything except the screens that have moved to the web tier.

**Web tier** — the part drawn in a `QWebEngineView`, styled with real CSS.
Analysis Results, Session Setup and Browse today; ADR 0016 lets each other screen move
in its own task. See ADR 0001 for why Results moved first.

**Renderer** — either tier, when the point is that there are two of them and
one palette must serve both. Never used for `QSvgRenderer`; say
`QSvgRenderer` when that is what is meant.

**Bridge** — the one object through which the two tiers exchange messages.
Each message is its own named member; nothing crosses as a generic
"send this kind of message" call. Not the **seam**, which is the visible
edge where the tiers meet on screen: the bridge is what crosses it, the
seam is what must not be seen.

**Web asset** — a stylesheet, page or script the web tier loads. The
printed-label templates are not web assets: they are rendered to PDF, never
shown in the web tier, and keep their own font.

**Web kit** — `gui/web/kit.css`, the stylesheet every web page links first:
cards, buttons, badges, inputs, menus, the toast, the banner, the state panel,
the page header. Components only, never a page's layout. Its sheet,
`tests/web/kit_sheet.html`, shows one of each.

**Order frame** — the analysis result folded to one row per order, with its
lines counted rather than listed. What the Qt tier's table shows.

**Order payload** — the order frame as the web tier receives it: one entry
per order, with that order's lines nested inside it.

## Results

**Results document** — the Results page: two cards on the sunken plane, the KPI
strip and one split card that holds the order table and, beside it, the detail
pane. It owns its view state (ADR 0005). Not the "results table", which named the Qt table it
replaced.

**Fulfillable order** — an order the session can ship complete. This is the
display word everywhere; the v2 canvas's "Ready" and "Ship complete" are not
used. Its complement is a **blocked order**. An order is fulfillable when
every one of its **SKU lines** is; one blocked SKU line blocks the whole order.
Status is stored per line but is only ever read per order.

**SKU line** — an order line that names a SKU, so it takes stock. A line
without one (a fee, a custom item) is not a SKU line: it never blocks an
order and never draws stock.

**Label count** — one courier label per fulfillable order, split by courier.
What the Labels card counts.

**Customer** — the order's recipient, from the orders-file column mapped to
`Customer` (Shopify's `Shipping Name` by default). Shows a dash when the
profile maps nothing to it.

**Order age** — how long ago the order was created in the shop, from the
column mapped to `Created_At`. Distinguished from **stock age**: how old the
stock file was when the analysis ran.

**Detail pane** — what the results document's slot shows by default: the
cursor order's identity, verdict, lines, tags, notes and actions. It shows one
order, never the multi-selection. It replaces the Qt tier's order detail pane.
It collapses to a rail that still says what it is.

**Verdict** — the pane's one sentence saying whether an order ships and, if
not, why. It is built from the run's reason codes, not from the status.

**Reason code** — one cause the run recorded for not shipping an order: short,
out of stock, invalid quantity, or no SKU. It names the SKU, and the quantities
where it has them.

**Set by a person** — an order whose status disagrees with its reason codes. It
was either marked fulfillable although the run blocked it, or held although
nothing was short. Drawn with a solid mark. Its opposite is **detected by the
run**.

**Stock left** — a SKU's opening stock minus the SKU lines of every
fulfillable order (`Final_Stock`). It is what Mark fulfillable draws on, and
it stays true through every edit and undo (ADR 0010). Not the stock an order
saw at its own turn, which is what its reason code quotes.

**Lot allocation** — which lots (expiry, batch) each SKU line of a fulfillable
order ships from. Derived, never stored: `analysis.with_lots` re-allocates FIFO
from the session's opening lots (its `input/inventory.csv`) after every change,
and every line owns its own list (ADR 0015). Not **Stock left**, which is the
per-SKU total after the draws.

**Lot label** — the expiry and batch a report names for some of a line's
units: its **Lot allocation**, fitted to the line's current quantity
(ADR 0014). Units the opening lots can't cover, or a session with no stock
file, have no lot label.

**Column manager** — a popover under the Columns button. It chooses and orders
the table's columns and is saved per client. The pane stays visible behind it.

**Pinned column** — Status and Order: always first and always shown.

**Additional column** — an orders-file column with no mapping, which the
analysis carries through under its own name when it is enabled. An order-level
one is filled down onto every line of its order.

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
lost by not drawing it. No screen of this app draws a shape since Browse moved
to the web tier; a session row's **badge** carries a dot instead.

**Chip** — the one status silhouette: an outlined pill carrying a mark and a
label. Distinguished from a **filter chip**, which is interactive and
dismissible, and from the **edge** variant, a lane marker that carries no
status of its own.

**Badge** — the web tier's status pill: a tinted fill, no outline and no mark.
Authorship, which the mark carries on a chip, is said in the pane's verdict
instead. A session row's badge adds a dot whose fill says how far the session
has come: hollow before packing starts, half while it is in flight, solid once
it is closed. Not a **chip**, which stays the Qt tier's silhouette.

**Selection ring** — the closed rectangle around a selected table row. Its
horizontal sides come from QSS, its two end caps from a delegate, because
`QTableView::item` styles cells and a QSS left border would repeat at every
column boundary. Distinguished from the **status edge**, the 3px role-coloured
bar on the row's leftmost visible column, which insets inside the ring. The Qt
tier's only: on the web tier the **cursor** row wears a bar on its left edge.

**Cursor** — the one order the detail pane shows, moved by a click or ↑ ↓. Not
a selection: a bulk action never reaches it.

**Checked orders** — the set a bulk action reaches, built with the row
checkboxes, Ctrl-click, Shift-click and Ctrl+A. It is what Python hears as the
selection. A filter that hides an order unchecks it.

**State panel** — the widget a screen shows instead of its table when there
is nothing to show: nothing-loaded, working, no-results, or failed. Names the
cause, names the file or filter that caused it, and offers the action that
resolves it.

**Selection bar** — the bar that exists only while orders are checked. It takes
the table header's place, counts the checked orders and holds every verb that
acts on more than one. It never floats over rows. The results document has
one and the Browse page has one; they share the kit's parts and no script.

**Bulk popover** — one surface carrying a whole bulk action: what it will
affect, the choice it needs, and the verb naming the consequence. It replaces
a chain of blocking dialogs. For a verb that removes orders or lines it lists
what will change, and its own verb is the confirmation: no dialog follows,
because Undo is real.

## Messages

**Message route** — where one message to the operator goes: a toast, an inline
message, a confirm, or an error banner, plus the two non-routes, a disabled
action and deletion. Not a **destination**, which is a place on the rail; the
9.25 brief's "four destinations" means the four routes.

**Toast** — the route for something that worked and needs no decision. It
never blocks, hides itself, appears on the window that raised it, and carries
Undo when the operation can be undone.

**Inline message** — the route for a problem with a location on screen. It sits
beside that location and clears when the field it names is edited; the typed
input survives.

**Confirm** — the route for an act that destroys data Undo cannot reach. Its
accept button is the verb, never "OK". An undoable act never confirms.

**Error banner** — the route for a failure. It persists until dismissed, says
what to do rather than what the exception was, and points to Logs for the cause.

## Shell

**Shell** — the chrome around every screen: the sidebar, the command bar and
the page. Not a screen itself, and it never scrolls.

**Sidebar** — the shell's left column: the destinations, and a footer holding
what configures the client and this PC (Client settings, the theme, the server
connection). It collapses to a 56px **rail**, and that choice is saved per PC.

**Destination** — a place the sidebar navigates to and stays on. The sidebar
holds destinations in its list and configuration only in its footer, never
mixed.

**Overflow** — the menu beside an object holding what configures it.
Qualified when the scope matters: the **command-bar overflow** holds what the
sidebar footer does not (New session, the server connection, the keyboard
shortcuts); the **screen overflow** holds actions scoped to the screen you are
on.

**Logs** — the destination holding the log viewer, renamed from **Info** when
Statistics was deleted and one page was left. Supersedes "Info", which named a
folder of three unrelated pages.

**Log entry** — one line in the viewer: time, level, source, message. The same
four fields whichever stream produced it.

**Source** — which stream a log entry came from. **Activity** is what the
operator did (`log_activity`, ten call sites); **Execution** is what the
program logged (the root logger, through `QtLogHandler`). One viewer, one
switch, never two widgets.

**Follow-tail** — the viewer scrolling itself to the newest entry. On only
while the user is already at the bottom; it stops the moment they scroll up and
counts what arrived since.

**Connection state** — whether this PC can currently reach the file server.
One boolean, from `ProfileManager.is_network_available`, carried by one
signal. Every control that would touch the share is disabled from it; that
disabling is the guard, not a decoration on top of one.

## Session setup

**Order line** — one row of an orders export: one SKU at one quantity. An order
may carry the same SKU on several lines, and each one is real. Never collapse
two lines because they look alike.

**Folder merge** — loading every CSV in a folder into one file slot as a single
file.

**Owning file** — in a folder merge, the one file a key's rows are taken from:
the newest file that contains it. The key is the order number for orders and
the SKU for stock. The key's rows in any other file are an **overlapping
order** (or **overlapping SKU**) and are skipped. Rows are never dropped for
repeating each other inside one file.

**Delimiter setting** — per client and per file kind, either **Auto** (read
from each file) or an **override**: a fixed character someone set because Auto
reads that client's files wrong. See ADR 0009.

**File slot** — the record holding one of the two input files. One slot per
file, three states (missing, loaded, problem), and the only thing that knows
whether its file is usable. Not a **file picker**, which is the dialog that
fills a slot: the slot persists and changes state, the picker appears and closes.

**File card** — a file slot as the Setup page draws it: a badge for its state,
the file's name, its rows, its orders or SKUs, its delimiter, and under a
problem the sentence that explains it and the link that fixes it.

**Setup state** — the one map Python builds for the Setup page: which view
shows, both file cards, the run summary's sentences, and whether a run may
start. The page draws it and works out no rule of its own. Every sentence that
depends on a fact comes from Python; the page's own words are fixed labels,
plus the progress line and the Run and Cancel captions, worded from the run's
step.

**Run summary** — the fixed column beside the file cards that says what the
run will do, holds Run analysis with the reason it is disabled, and becomes
the progress view while a run is going.

**Step** — one of a run's four named stages: reading the files, checking the
fulfilment history, allocating stock, saving the results. Cancel takes effect
between steps and never once saving has begun.

**Strategy** — how a run allocates stock across competing orders, either
`multi-item-first` or `fifo`. Supersedes "analysis mode", which named the
combo rather than the thing it chose and collided with the Orders/Stock
"Load Mode" on the same screen.

**Inventory memory** — the stock level per SKU carried from one run to the
next, so a run can proceed without a fresh stock export. It covers **every SKU
in the stock file**, not only the SKUs an order touched: a SKU the run left
alone keeps its opening level. Each run's stock file is the truth, so a SKU
that leaves the file leaves memory — memory accumulates levels, never SKUs.
A SKU listed on several stock rows is remembered at their sum.
A loaded stock file is always used as it is; memory stands in only when a run has no stock file.

**Memory baseline** — the opening stock a session's first run started from,
kept in the session. A re-run of that session starts from its baseline, not
from memory it has already drawn down.

## Sessions

**Blocked order** — an order this session cannot fulfil, counted as
`blocked_orders`. One number, one name: `SHORT ON STOCK` and `BLK` are both
retired. `not_fulfillable_orders` stays the persisted key, because it is a
file shared with another tool.

**Display status** — one of the eight states a session row shows, derived from
the four stored statuses plus packing progress and idle time. Distinguished
from **stored status**, the four values `SessionManager.VALID_STATUSES`
accepts and a person can set.

**Browse state** — the map Python builds for the Browse page: which view
shows, and one record per session with its age, badge, counts, packing and
attention reason already worded. The page filters, counts and groups those
records and decides no fact about a session.

**Needs attention** — the group Browse draws first: sessions that are paused,
stale or incomplete, and sessions still in flight that carry blocked orders.
Each row's reason is named in the group's heading.

**Session state** — the session's analysis as saved in
`analysis/current_state.pkl`. Every edit rewrites it whole, from one PC's copy.
Not **stored status**, which lives in `session_info.json`.

**Stale** — this PC's copy of the session state is older than the one on the
server, because another PC saved it after this PC loaded or last saved it. A
stale PC's saves and exports are refused until it reopens the session.

**Repeat order** — an order another live session has already handled: it is
in another session's fulfillment history, or the Packer packed it in any
session. Marked, never held: a repeat order stays fulfillable. A **live
session** is one that exists and is not stored as abandoned. ADR 0012.

**Fulfillment history** — per client, the orders each session currently
ships: one row per order per session, dated when that session first recorded
it. It follows the session state, not the run. Distinguished from the
**Packer signal**, the orders Packing Tool has actually packed, which each
session's `session_info.json` records.

## Printing

**Print mode** — how a label PDF reaches a printer: through the operating
system's print dialog (**driver**), or as raw ZPL sent straight to a printer
target (**Raw ZPL**). Chosen per tool and per PC.

**Print options** — one tool's print mode and the settings that mode needs.
Stored on the PC, not in the client profile.

**Actual size** — a label PDF printed at its own page dimensions, scaled
uniformly only when the chosen paper differs, and never shrunk into page
margins. What Adobe's "Actual size" does, and what driver mode prints.

**Reference strip** — the band Reference Labels adds along the bottom of a
matched courier page, carrying the REF number and its barcode. The courier
content is shrunk to make room for it, so a stamped label is smaller than the
courier's original on purpose.

**Label number** — the #N on a barcode or QR label: its order's position on
the packing list the labels were generated from, courier first, as the list
is printed. Not the order number's rank.

**Name fallback** — matching a courier page to a REF by the recipient's name,
used only when no PostOne ID or tracking number matches. It counts only when
exactly one CSV name appears on the page as whole words and that name carries
exactly one REF. A name-fallback match is always **unverified**.

**Archived export** — an earlier stock export of the same report, moved to
`stock_exports/old/` when the report is exported again. Only the newest
export stays in `stock_exports/`, so importing the folder never writes stock
off twice.

**Fold** — a closed row that states the current values of the controls it
hides. It is opened to change a value, never to check one. Distinguished from
an **overflow**, which holds actions rather than values.

## Settings

**Unsaved page** — a settings page whose values differ from the ones it
opened with. The nav marks it, the footer names it, and closing guards it.
Saving writes every page regardless; unsaved is what the operator is warned
about, not what decides the write.

**Close guard** — the row that replaces Save and Cancel when closing Settings
would discard unsaved pages: Keep editing, Discard, Save & close.
Distinguished from a **confirm**, which is a separate dialog; the guard is
inline because the pages it names are on screen beside it.

**Match count** — how many orders and rows a report's filters select from
the current analysis, counted over fulfillable orders exactly as the generated
file is. Shown while the filter is being written.

**Generate order** — the order reports are listed in Settings › Reports,
which is the order they are offered and generated in. Set by dragging within
one kind; packing lists and stock exports never mix.

**Packaging write-off** — the packaging material SKUs a run consumes, derived
from the orders' internal tags. A stock export either carries them among its
product rows, writes them to a file of their own beside it, or leaves them out.
Supersedes "SKU writeoff", which names the config key rather than the thing.

## Rules

**Article rule** / **Order rule** — a rule whose conditions test one order
line at a time, or the whole order. Article rules run before order rules.

**Negative operator** — `does not equal`, `does not contain`, `not in list`,
`not between`, `does not match regex`. On an order rule it means *no line*
matches the positive form, whatever the field.

**Rule hold** — a rule setting an order Not Fulfillable after the run has
allocated stock. It holds every line of the order, returns the order's stock
to Stock left, and records itself as a reason code, so the order reads as
detected by the run, not set by a person. A rule can hold an order; it can
never make one fulfillable.

**Bonus line** — a line an `ADD_PRODUCT` rule adds to an order. It takes stock
like any SKU line. An order whose bonus the stock can't cover is held whole.

## Repos

**Canonical source** — `shopify-fulfillment-tool`. Every `shared/` change is
authored here; packing-tool receives it through its own `scripts/sync_shared.py`,
one-way, pinned to a commit. A `shared/` file edited in packing-tool is
overwritten by its next sync.
