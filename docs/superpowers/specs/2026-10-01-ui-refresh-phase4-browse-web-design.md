# UI refresh phase 4: Browse on the web tier

**Task:** dev-runner run 44, Todoist 6hfx8crRqqMJqG9M: "UI refresh phase 4: move Browse to the web tier".
Brief: `docs/design/ui-refresh/roadmap.md`, phase 4. Depends on phase 2 (merged, #356); built on phase 3 (#357).
**Path:** architectural. It adds a third web view and a third bridge, replaces the Qt session tree, and gives
session status and comment changes an Undo.
**Mockup followed:** `docs/design/ui-refresh/mockups/browse.html` (all seven states, both themes). Every
departure is in §9.

## 1. What this task delivers

1. The Browse page as a web page on the kit: `gui/web/browse.html`, `browse.css`, `browse.js` (§5).
2. `BrowseBridge`, and one pure function that builds every fact a session row shows (§3, §4).
3. `SessionBrowserWidget` rewritten around the view. Its name, signals and public methods stay (§6).
4. Undo for a status or comment change: `SessionManager.restore_session_fields` (§6.3).
5. The Age cell as the mockup draws it, with the archive countdown in its tooltip (§4.3).
6. Shell wiring: the page inset, the toast router, F5, and where an un-analysed session opens (§7).
7. Deleted Qt code and tests (§8). Docs (§11).

## 2. Owner's decisions (2026-10-01, run 44)

| Question | Answer |
|---|---|
| Export Combined Stock, which the mockup's selection bar does not draw | Keep it in the bar, shown with 2 or more sessions checked |
| Column sorting, which the mockup does not draw | Dropped. Rows are newest first inside each group |
| The auto-archive countdown in the Age cell | The cell is the mockup's short age. In a session's last 7 days it takes the warning colour and the tooltip says "Archives in 4 d" |
| The design (§3 to §10) | Approved |

The third `QWebEngineView` follows the owner's phase 3 decision: build on the Linux numbers (about 31 MB and
at most 0.15 s for each view after the first, ADR 0016); the Windows check is the release's.

## 3. Architecture

```
SessionLoaderWorker ──► SessionBrowserWidget ──► browse_state(...) ──► BrowseBridge.state ──► browse.js render()
 (unchanged, a thread)   (hosts the view)         (pure, a dict)        (one Property)         (draws it)
browse.js ──► BrowseBridge slot ──► Signal ──► SessionBrowserWidget ──► SessionManager ──► quiet reload
```

- **Python owns every fact about a session.** `browse_state` returns one dict: which view to show and one
  record per session, with its age text, badge, counts, packing and attention reason already worded.
- **The page owns the view state**, as the Results page does: the tab, the search text, the checked rows,
  whether archived rows are shown, and which popover is open. It filters, counts and groups the rows it
  already holds, so typing in the search box never crosses the bridge.
- **The page names a session by its name, never by a path.** The widget maps a name to the entry it loaded.
  A name it does not hold is dropped.
- **The widget is the controller.** `mw.session_browser` keeps being a `SessionBrowserWidget`, so
  `set_client`, `refresh_sessions`, `mark_dirty` and the three signals the window connects need no rewiring.

### 3.1 Files

| File | What it is |
|---|---|
| `gui/browse_state.py` (new) | `browse_state(...)` and its row builder. No Qt import |
| `gui/browse_bridge.py` (new) | `BrowseBridge(PageBridge)`, `mount_browse_page(view)` |
| `gui/web/browse.html`, `browse.css`, `browse.js` (new) | The page |
| `gui/session_browser_widget.py` | Rewritten: the view, the loader, the writes, Undo. `SessionLoaderWorker` stays as it is |
| `shopify_tool/session_lifecycle.py` | `age_cell` replaces `age_label`; `_IN_FLIGHT` becomes `IN_FLIGHT` |
| `shopify_tool/session_manager.py` | `restore_session_fields` |
| `gui/ui_manager.py` | Tab 2 joins `_WEB_PAGES`; the tab's own margins go |
| `gui/main_window_pyside.py` | `web_toast` knows tab 2; F5; an un-analysed session opens on Setup |
| `gui/shortcuts_dialog.py` | The F5 row |
| `.github/workflows/build_release.yml` | The bundle check also looks for `browse.html` |
| Deleted | `gui/session_row_delegates.py`, `gui/components/selectionbar.py` |

Nothing in `shared/` changes. `gui/web/kit.css` does not change: the tab, the badge dot and the skeleton have
one user, so they live in `browse.css` until a second page needs them.

### 3.2 `BrowseBridge`: the catalogue

Channel name `browse`. Add a member here before adding it to the code.

| member | direction | meaning |
|---|---|---|
| `state` Property (`QVariantMap`, notify `stateChanged`) | Python → JS | Everything the page draws (§4) |
| `themeCss`, `toastRaised(text, undoable)` | Python → JS | From `PageBridge`. A status or comment change raises an undoable toast |
| `refresh()` → `refreshRequested()` | JS → Python | Refresh, and the failed panel's Try again |
| `openSession(name)` → `openRequested(str)` | JS → Python | Double-click, Enter, or Open |
| `setStatus(names, status)` → `statusRequested(list, str)` | JS → Python | The Status menu. `status` is one of `SessionManager.VALID_STATUSES`; anything else is dropped |
| `setComment(names, text)` → `commentRequested(list, str)` | JS → Python | The Comment popover's Save. An empty text clears the comment |
| `exportCombined(names)` → `exportRequested(list)` | JS → Python | Export combined stock. Fewer than two names is dropped |
| `newSession()` → `newSessionRequested()` | JS → Python | The empty panel's button |
| `undo()` → `undoRequested()` | JS → Python | The toast's Undo |

`names` arrives as a `QVariantList`. The bridge keeps the entries that are non-empty strings and drops the
call when none is left. `set_state(state: dict)` is the Python-facing setter; it emits `stateChanged` only
when the dict differs from the last one.

## 4. The state

### 4.1 `browse_state`

```python
def browse_state(*, client: str, loading: bool, failed: bool,
                 sessions: list[dict], now: datetime) -> dict
```

`sessions` is what `SessionManager.list_client_sessions` returns: newest first. `browse_state` keeps that
order and never sorts.

```python
{
  "view": "no_client" | "failed" | "loading" | "empty" | "list",
  "client": "ACME",
  "rows": [row, ...],          # [] unless view is "list"
}
```

**View**, first match wins: `no_client` with no client; `failed` when the last load failed; `loading` while
a loud load runs; `empty` with no sessions; otherwise `list`.

### 4.2 A row

```python
{
  "name": "2026-09-30_1",
  "age": "6 h", "age_title": "Created 2026-09-30 08:12", "age_warn": False,
  "status": "in_progress",                 # session_lifecycle.display_status
  "label": "In progress", "tone": "info", "dot": "half",
  "tab": "active",                         # the stored status, or "" when it is not one of the four
  "orders": "197", "items": "402",         # "" when zero or unknown
  "blocked": "9", "blocked_alert": True,   # "" when zero or never analysed
  "pack": "2 / 3", "pack_pct": 67, "pack_tone": "", "pack_title": "2 of 3 packing lists completed in Packing Tool",
  "comment": "Morning wave, DHL pickup 15:00",
  "why": "blocked",                        # "" | "paused" | "stale" | "incomplete" | "blocked"
}
```

An entry that is not a dict, or has no string `session_name`, is skipped.

| field | rule |
|---|---|
| `status` | `display_status(entry, now)` |
| `label` | The status with `_` as a space, first letter capital: "Not started", "In progress". An unknown status reads as its own name |
| `tone` | `not_started` neutral, `in_progress` info, `paused` warning, `stale` warning, `completed` success, `incomplete` danger, `abandoned` neutral, `archived` neutral. Unknown: neutral |
| `dot` | `not_started` hollow; `in_progress`, `paused`, `stale` half; the other four solid. Unknown: hollow |
| `tab` | The stored `status` when it is in `SessionManager.VALID_STATUSES`. A missing, empty or non-string status reads `active`, as `display_status` reads it. Any other value: `""` (the row shows in All only) |
| `orders`, `items` | `statistics.total_orders` and `statistics.total_items` as a positive int with a comma for thousands; else `""` |
| `blocked` | `blocked_orders(entry)` when it is above zero; else `""` |
| `blocked_alert` | `blocked` is set and the status is in `IN_FLIGHT`. The page draws it red and bold |
| `pack` | `"{packed} / {total}"` from `packing_completion(entry)` when `total > 0` and the status is not `abandoned`; else `""` |
| `pack_pct` | `round(packed / total * 100)`, or 0 with no `pack` |
| `pack_tone` | `success` when `packed >= total`; `danger` when the status is `incomplete`; else `""` |
| `pack_title` | "{packed} of {total} packing lists completed in Packing Tool", or `""` with no `pack` |
| `comment` | `comments` when it is a string, stripped; else `""` |
| `why` | The status when it is `paused`, `stale` or `incomplete`; `blocked` when `needs_attention(status, blocked)` holds for another status; else `""` |

Packing counts packing lists, as it does today. The mockup's "142 / 188" reads like orders; the data holds
lists.

### 4.3 `session_lifecycle.age_cell`

```python
def age_cell(entry: dict, now: datetime) -> tuple[str, str, bool]:
    """(cell, tooltip, warn) for the Age column."""
```

- An unreadable `created_at`: `("—", "Created date unreadable", False)`.
- The cell, from `now - created` (a negative span reads as zero): under one hour `"<1 h"`; under 24 hours
  `"{hours} h"`; otherwise `"{days} d"`. Days never roll up into weeks or months: "52 d".
- The tooltip: `"Created 2026-09-30 08:12"`.
- `warn` is true when the automation will archive this session within `ARCHIVE_WARNING_DAYS`: the stored
  status is `active` or `completed`, `status_manually_set` is not set, and
  `0 < AUTO_ARCHIVE_AFTER_DAYS - days <= ARCHIVE_WARNING_DAYS`. The tooltip then ends
  `" · Archives in {remaining} d"`.

`age_label` showed the countdown on every session of that age, including abandoned ones and ones a person
set by hand, which `derive_status_updates` never archives. `age_cell` asks the same two questions the
automation asks. `age_label` is deleted.

`_IN_FLIGHT` is renamed `IN_FLIGHT`: `browse_state` reads it.

## 5. The page

Geometry is the mockup's at 1366×768 unless §9 says otherwise. Colours are kit tokens. A divider is
`--border-subtle`, a control's edge is `--border` (ADR 0018).

### 5.1 Frame

`body` is `--surface-sunken`. `#browse` fills the view, has padding `16px 24px 20px`, and scrolls sideways
(`overflow-x: auto`) when the view is narrower than the card's `min-width: 780px`. `_WEB_PAGES` becomes
`frozenset({0, 1, 2})`, so the page area's inset is 0 on Browse.

`#browse` carries `data-view`. Three views are a `.card` that fills the page and centres a kit `.state` panel,
its title in heading size:

| view | glyph | title | text | button |
|---|---|---|---|---|
| `no_client` | folder-open | "Choose a client" | "Pick a client in the bar above to see its sessions." | none |
| `empty` | folder-open | "No sessions yet" | "CLIENT_{client} has no sessions on the file server." | "New session" (primary, plus glyph) → `newSession()` |
| `failed` | alert triangle | "Sessions didn't load" | "Details are in Logs." | "Try again" (secondary) → `refresh()` |

The rail does not offer Browse without a client or a connection, so `no_client` shows only for the moment
before the rail moves away. It is kept because the mockup draws it and it costs one branch.

The views `loading` and `list` are one `.card`, a column that fills the page: toolbar, header row or
selection bar, the scrolling list, footer.

### 5.2 Toolbar

A row, gap 8, padding 8, a `--border-subtle` rule under it.

- **Tabs** (`role="tablist"`, gap 2): All, Active, Completed, Abandoned, Archived. Each is a `.tab` button
  (`role="tab"`): `--control-height` high, padding `0 10px`, radius `--kit-radius`, a transparent 1px edge,
  `--text-secondary`, gap 6 between the label and its count. Hover: `--hover`. Selected
  (`aria-selected="true"`): `--surface-raised`, a `--border` edge, `--text`, bold. The count is the kit's
  `.segment-count`. Left and Right move to the neighbouring tab and select it.
- A spacer, then **search**: a kit `.input` with the search glyph, placeholder "Search sessions",
  `flex: 0 1 260px`, `min-width: 150px`.
- **Count label**: caption, `--text-secondary`, right-aligned, `min-width: 84px`. Hidden under a page width
  of 980px.
- **Refresh**: `.btn.secondary` with the refresh glyph, title "Refresh  F5" → `refresh()`. Disabled while
  loading.

| | rule |
|---|---|
| A row is **in a tab** | All: `tab != "archived"`, or any row once archived rows are shown. The other four: `tab` equals the tab's key |
| **Tab count** | The rows in that tab, ignoring the search. All never counts archived rows. While loading every count reads "–" |
| **Visible rows** | In the current tab, and the search text (trimmed, lower case) is in the name or in the comment (lower case) |
| **Count label** | Loading: "Reading…". With a search: "{visible} of {in tab} sessions". Otherwise "{in tab} sessions". One session reads "1 session" |

Choosing a tab, typing in the search box and Show or Hide each uncheck every row and close any popover. So
does a loud reload (the `loading` view). A state for another client also returns the page to the All tab with
an empty search and archived rows hidden: session names are dates and repeat between clients, so one
client's checked rows must never carry over to the next.

### 5.3 Header row and selection bar

Both are 36px high on `--surface-raised` with a `--border-subtle` rule under them, and share one grid with
the rows: `36px 150px 64px 124px 72px 72px 72px 150px minmax(0, 1fr)`.

**Header row** (nothing checked): a checkbox, then Session, Age (right), Status, Orders (right), Items
(right), Blocked (right), Packing, Comment, in caption bold `--text-secondary`. The checkbox checks every
visible row. It is disabled while loading or with no visible row.

**Selection bar** (one or more visible rows checked) takes the header row's place:

- the checkbox, checked when every visible row is checked and indeterminate otherwise; clicking it unchecks
  everything (title "Clear selection");
- "{n} selected" in bold;
- **Open** (`.btn.secondary.compact`), with exactly one checked → `openSession(name)`;
- **Status** with a chevron → the Status menu;
- **Comment…** → the Comment popover;
- **Export combined stock**, with two or more checked → `exportCombined(names)`.

The checked set that counts is the checked rows that are visible. A row hidden by the tab or the search is
not acted on.

### 5.4 Status menu

A kit `.menu`, 300px wide, under the Status button. A `.menu-group` title: "Set status for {name}" with one
row checked, "Set status for {n} sessions" otherwise. Four `.status-item` buttons, each a column (gap 1,
padding `6px 10px`, radius `--radius-md`, hover `--hover`): a badge on the first line, a note in caption
`--text-secondary` on the second, which wraps.

| badge | sends | note |
|---|---|---|
| Active (info, half dot) | `active` | "Shows as Not started, In progress, Paused or Stale from activity" |
| Completed (success, solid) | `completed` | "Shows as Incomplete if packing is not finished" |
| Abandoned (neutral, solid) | `abandoned` | "Kept on the server. Repeat-order checks ignore it" |
| Archived (neutral, solid) | `archived` | "Hidden from All until you choose Show" |

Choosing one calls `setStatus(names, status)` and closes the menu. The rows stay checked.

### 5.5 Comment popover

A kit `.popover`, 340px wide, under the Comment… button.

- Body (padding `12px 14px`, gap 8): the title in label size, bold: "Comment on {name}" or "Comment on {n}
  sessions". A three-row `textarea` (placeholder "Visible to everyone who opens this client", no resize,
  `--border` edge, radius `--kit-radius`, padding `6px 8px`, `--surface`), which opens holding the session's
  comment with one row checked and empty with several, and takes focus. A note in caption `--text-secondary`:
  "Shown in the Comment column." with one; "Replaces the comment on {list}." with several, where the list is
  up to three names joined by ", ", or the first two and "and {n} more".
- Foot (padding `10px 14px`, a `--border-subtle` rule above, buttons right-aligned, gap 8): **Cancel**
  (secondary) and **Save** (primary). Save calls `setComment(names, text.trim())` and closes the popover.
  Ctrl+Enter in the textarea saves.

Only one of the menu and the popover is open at a time. Escape, a click outside, or its own button again
closes it; Escape returns focus to its button. A state push from Python leaves an open popover and its draft
alone.

### 5.6 The list

The list area fills the rest of the card and scrolls (`overflow: auto`).

**Groups.** The visible rows with a `why` are "Needs attention", drawn first; the rest follow. A group with
no row is not drawn. A group head is a row (`--row-height`, padding `0 12px`, gap 8, `--surface-sunken`, a
`--border-subtle` rule under it): for Needs attention an 8px `--status-warning` dot; the label in bold; the
count in mono caption `--text-secondary`; the note in caption `--text-secondary`.

- The second group is labelled "Everything else" when Needs attention is drawn, and with the tab's label
  otherwise.
- The Needs attention note counts its rows by `why`, in this order, joined by " · " and leaving out a zero:
  "{n} paused", "{n} stale", "{n} incomplete", "{n} with blocked orders".

**A row** is `--row-height` high with a `--border-subtle` rule under it, on the grid of §5.3. Hover:
`--hover`. Checked: `--selection-bg` and a 3px `--selection-border` strip on its left edge (a positioned
`::before`, not a shadow). Clicking a row toggles its checkbox; double-clicking opens it.

| cell | drawing |
|---|---|
| checkbox | The kit checkbox, `aria-label` "Select {name}" |
| Session | Mono, bold |
| Age | Mono, right-aligned, `--text-secondary`; `--status-warning` when `age_warn`. `title` is `age_title` |
| Status | A kit `.badge` in the row's tone, holding a `.badge-dot` and the label |
| Orders, Items | Mono, right-aligned. Empty: "—" in `--text-disabled` |
| Blocked | Mono, right-aligned. `blocked_alert`: `--status-danger`, bold. Empty: "—" in `--text-disabled` |
| Packing | `pack` in mono (72px wide), then a track (4px high, up to 48px wide, radius 2, `--border`) with a fill `pack_pct` wide: `--status-success-dot` for `success`, `--status-danger-dot` for `danger`, `--text-secondary` otherwise. `title` is `pack_title`. With no `pack`: "—" in `--text-disabled` and no track |
| Comment | `--text-secondary`, one line, ellipsis; `title` is the whole comment. Empty: "—" in `--text-disabled` |

`.badge-dot` is a 6px circle with a 1px `currentColor` edge. `solid`: filled with `currentColor`. `hollow`:
empty. `half`: its left half filled, by a clipped `::after` (the lint bans gradients).

**Loading.** A line 40px high (padding `0 12px`, `--text-secondary`, a `--border-subtle` rule under it): the
loader glyph and "Reading sessions from the server…". Under it ten skeleton rows on the row grid, each cell a
bar 8px high, radius 4, `--border-subtle`, with the mockup's widths: 96 for the name; 28 for Age, Orders,
Items and Blocked; `64 + (i % 3) * 8` for Status and Packing; `60 + (i * 37) % 120` for Comment.

**No visible row** (view `list`): a kit `.state` panel in the list area, padding `80px 24px`.

| situation, first match | glyph | title | text | button |
|---|---|---|---|---|
| a search is typed | search-x | "No sessions match" | "Nothing in {Tab} has “{search}” in its name or comment." | "Clear search" (secondary): empties the search |
| tab All, and every session is archived | folder-open | "Nothing in All" | "Every session of this client is archived." | "Show archived" (secondary): shows them |
| otherwise | folder-open | "Nothing in {Tab}" | "No session of this client is {tab, lower case}." | none |

### 5.7 Footer

36px high, padding `0 12px`, a `--border-subtle` rule above, caption `--text-secondary`.

- On the All tab, when the client has archived sessions and the page is not loading: "{n} archived", "·",
  and a `.btn.link` **Show**. Once shown: "{n} archived shown" and **Hide**.
- A spacer, then "Double-click a session to open it".

### 5.8 Toast and keyboard

The page draws the kit `.toast`: the text, an **Undo** `.toast-action` when the toast is undoable →
`undo()`, and a dismiss button (`id="toast-dismiss"`, × glyph, label "Dismiss"). It hides after 4 s, as on
Setup and Results; a new toast replaces the old one. Undo dismisses the toast.

Every control is a real `<button>`, `<input>` or `<textarea>`. Tab order: tabs, search, Refresh, the header
checkbox or the selection bar's controls, the rows' checkboxes, the footer link.

| key | where | does |
|---|---|---|
| ← → | a tab | moves to the neighbouring tab and selects it |
| ↑ ↓ | a row's checkbox | moves focus to the checkbox of the row above or below, across groups |
| Space | a row's checkbox | toggles it (the checkbox's own behaviour) |
| Enter | a row's checkbox | opens that session |
| Escape | anywhere | closes the open menu or popover and focuses its button |
| Ctrl+Enter | the comment textarea | saves |

After a render, focus returns to the element with the same `data-key` (a row's checkbox is keyed by its
session name), as on Setup.

`# ponytail:` the list is redrawn whole on every change, with no row virtualisation. A client has tens of
sessions and archived ones are hidden by default. Window the rows, as the Results table does, if a client
ever shows thousands.

## 6. The widget

`SessionBrowserWidget(QWidget)` keeps `session_selected(str)`, `multi_export_requested(list)`,
`new_session_requested()`, `USE_ASYNC`, `set_client(client_id, auto_refresh=True)`, `refresh_sessions()`,
`mark_dirty()`, `showEvent` and `closeEvent`. Its layout holds one `QWebEngineView` with no margins. It
exposes `view` and `bridge`.

State it holds: `current_client_id`, `sessions_data`, `worker`, `_is_dirty`, `_loading`, `_failed`, `_undo`.
`_push()` builds `browse_state(...)` from them and calls `bridge.set_state`.

### 6.1 Loading

- `set_client`: when the client changes it empties `sessions_data`, clears `_undo` and `_failed`, sets
  `_loading` when the new client is not empty, marks dirty and pushes, so the page never shows the previous
  client's rows. It then refreshes at once when `auto_refresh` is set or the widget is visible, as today.
- `refresh_sessions(quiet=False)`: with no client it empties the list and pushes. Otherwise it cleans up a
  running worker and starts a `SessionLoaderWorker` for every status (`status_filter=None`: the tabs filter in
  the page). A loud refresh sets `_loading`, clears `_failed` and pushes first, so the skeleton shows. A quiet
  one leaves the rows on screen until the new ones arrive.
- `_on_sessions_loaded`: hidden, it marks dirty and returns, as today. Otherwise it stores the sessions,
  clears `_loading` and `_failed`, and pushes.
- `_on_load_error`: clears `_loading`, sets `_failed`, empties `sessions_data`, pushes. No dialog: the page
  shows the failed panel.
- With `USE_ASYNC` false the load runs in line through the same two handlers.

The status combo is gone, so the server-side `status_filter` argument is no longer used by Browse.
`list_client_sessions` reads the whole index either way.

### 6.2 What the page asks for

`_entries(names)` returns the loaded entries whose `session_name` is in `names`, in list order.

| request | does |
|---|---|
| `refreshRequested` | `refresh_sessions()` (loud) |
| `openRequested(name)` | Emits `session_selected(path)` for that entry |
| `newSessionRequested` | Emits `new_session_requested` |
| `exportRequested(names)` | Emits `multi_export_requested(paths)` when two or more entries match |
| `statusRequested(names, status)` | For each entry: `update_session_status(path, status, manual=True)`. Then the toast, the Undo record and a quiet refresh (§6.3) |
| `commentRequested(names, text)` | For each entry: `update_session_info(path, {"comments": text})`. Then the same |
| `undoRequested` | §6.3 |

A write that raises is logged and counted. When some fail, the window's error banner says so (`show_error`):
"The status wasn't updated" or "The comment wasn't saved" for one session, "{failed} of {n} sessions weren't
updated" for several, each with "Details are in Logs." The writes run on the GUI thread, as they do today.

Toasts, raised with `bridge.raise_toast(text, True)` when at least one write succeeded. `{what}` is the
session's name for one, "{n} sessions" for several, counting the ones that were written:

- "Set {what} to {Active | Completed | Abandoned | Archived}"
- "Comment saved on {what}", or "Comment cleared on {what}" when the text is empty

### 6.3 Undo

Before a write, the widget snapshots each entry's `status`, `status_manually_set`, `status_updated_at`,
`comments` and `last_updated` (a missing key as `None`). After it, `_undo` is `{path: snapshot}` for the
sessions that were written. One change is remembered; the next one replaces it, and a client change clears it.

`undoRequested` calls `SessionManager.restore_session_fields(path, snapshot)` for each, clears `_undo`, and
refreshes quietly. A failure is logged and counted, and the banner reads "The change wasn't undone" (one) or
"{failed} of {n} sessions weren't restored". With no `_undo` it does nothing.

```python
def restore_session_fields(self, session_path: str, fields: dict) -> bool
```

Under the session's lock it reads `session_info.json`, sets each key in `fields` to its value, removes a key
whose value is `None`, writes the file atomically and updates the index entry. It stamps nothing, so a
restored session's `last_updated` is what it was and the session is Stale again if it was Stale. It raises
`SessionManagerError` for a missing session, for a `status` that is not in `VALID_STATUSES`, and for a failed
write.

Restoring `status_manually_set` is what makes Undo real: an archive a person undoes goes back under the
automation's care, and a hand-set status stays hand-set.

## 7. Shell

- `gui/ui_manager.py`: `_WEB_PAGES = frozenset({0, 1, 2})`. `_create_tab3_session_browser` gives the tab a
  layout with no margins and no spacing.
- `MainWindow.web_toast`: tab 2 answers with `session_browser.bridge`. "Combined stock export saved: …" is
  then drawn by the Browse page.
- `MainWindow.load_existing_session`: a session with no analysis switches to Setup (tab 0), where its files
  and Run analysis are. Today it stays where it was. A session with an analysis still opens Results.
- F5: a window shortcut that calls `session_browser.refresh_sessions()` when Browse is the current tab.
  `SHORTCUTS` gains `("F5", "Refresh the session list, on Browse")`.
- The session chip stays in the command bar on Browse: its mockup has no page head.

## 8. Deleted

- From `gui/session_browser_widget.py`: the tree, `_SessionItem`, `_GroupItem`, the Age column sizing, the
  status combo, the archive line, the Qt selection bar, the empty panels, `QInputDialog`, the filter sentence.
- `gui/session_row_delegates.py` and `gui/components/selectionbar.py` (`ContextualSelectionBar`), with their
  exports in `gui/components/__init__.py`. The Session Browser was the last user of both.
- `session_lifecycle.age_label`.
- Tests: `test_session_browser_1e.py`, `test_session_browser_columns.py`, `test_components_selectionbar.py`,
  the `age_label` cases in `test_session_lifecycle.py`, and the `STATE_STYLES` cases in
  `test_status_channels.py` (its one test of `shared.theme.status_style` stays). `test_status_edge_delegate.py`
  stops importing the deleted roles. §10 lists what pins the behaviour instead.

Kept: `gui/selection_ring.py` and `gui/status_edge_delegate.py` (the log viewer uses them until phase 6),
`shared.components.FilterBar` and `shared.theme.paint_status_shape` (`shared/` is not this task's).

## 9. Departures from the mockup

| Mockup | Phase 4 | Why |
|---|---|---|
| The bar holds Open, Status, Comment… | And Export combined stock with two or more checked | Owner, §2 |
| Age is the age | The warning colour and a tooltip in the last 7 days before the auto-archive | Owner, §2 |
| Packing "142 / 188" | Packing lists: "2 / 3" | The data counts lists |
| "Double-click a session to open it in Results" | "Double-click a session to open it"; an un-analysed session opens on Setup | Results is not offered until an analysis exists |
| The dot's half fill is a gradient; a spinner; the Archived badge at 80% opacity | A clipped half; a still glyph; full strength | Gradients, transforms and opacity are banned on both tiers (ADR 0016) |
| The group dot is amber (`#B28400`) | `--status-warning` | The amber is under the 3:1 floor (ADR 0018). No new token |
| The checked row's edge is an inset shadow | A positioned strip | Only the two shadow tokens may be a `box-shadow` |
| "1 blocked orders" | "1 with blocked orders" | Grammar |
| "Kept on the server, left out of reports" | "Kept on the server. Repeat-order checks ignore it" | That is what abandoning does (`packed_orders.py`) |
| "Shown in the Comment column and in Setup." | "Shown in the Comment column." | Setup does not show the comment |
| An empty tab reads "No sessions match" with a Clear search button | "Nothing in {Tab}", with a button only when there is something to clear or show | A panel names its cause and offers the act that resolves it |
| No load-failure state | The failed panel | It replaces a modal error over an empty table |
| The head row's rule and the neutral badge's edge are `border` | `--border-subtle` | Dividers are hairlines (ADR 0018); the kit badge |
| 28px controls, 32px rows, the search box's strong edge | `--control-height`, `--row-height`, the kit `.input` | The density tokens and the kit |
| Blocked is red for a paused row and red and bold for an in-flight one | Red and bold for any in-flight row with blocked orders | One rule; the mockup's design note says only "red only there" |
| The toast stays until dismissed | It hides after 4 s | As Setup and Results |
| Segoe UI, Consolas; a 44px bar | Inter and the theme's mono face; 48px | The bundled faces; phase 1's bar |

Kept though the mockup does not draw them: the automatic status sync on load, the error banner for a failed
write, the `title` tooltips.

## 10. Tests (test-first; the seams)

| Seam | File | Asserts |
|---|---|---|
| Age | `test_session_lifecycle.py` | `age_cell`: "<1 h", "6 h", "1 d", "52 d"; a future date reads "<1 h"; the tooltip; an unreadable date; `warn` and the countdown at 23 to 29 days for `active` and `completed`; no warning for `abandoned`, `archived`, a hand-set status, 22 days, 30 days |
| State: views | `test_browse_state.py` (new) | Each of the five views from its inputs and their precedence; `rows` is empty outside `list` |
| State: rows | `test_browse_state.py` | Every field of §4.2 for each of the eight statuses and an unknown one; `tab` from a missing and an unknown stored status; counts with a comma; blocked empty at zero and at `None`; `blocked_alert` only in flight; packing for none, part, full, `incomplete`, `abandoned`; `why` for each reason; order is kept; a malformed entry is skipped |
| Restore | `test_session_manager.py` | `restore_session_fields` sets values, removes `None` keys, leaves other keys and `last_updated` alone, updates the index, rejects an unknown status and a missing session |
| Bridge | `test_browse_bridge.py` (new) | Each slot emits its signal with its arguments; an unknown status, an empty name list, non-string names and a one-name export are dropped; `set_state` emits once for a change and not for the same dict |
| Page: views | `test_browse_page.py` (new) | Through a real Chromium: each panel's title, text and button; New session and Try again call their slots; loading shows ten skeleton rows, "–" counts, "Reading…" and a disabled Refresh |
| Page: tabs and search | `test_browse_page.py` | The five counts; a tab filters and unchecks; the search matches a name and a comment; the count label in each form; the three no-row panels and their buttons |
| Page: groups and rows | `test_browse_page.py` | Needs attention first with its note; the second group's two labels; an empty group is not drawn; badge tone and dot; the warning age and its title; the blocked alert; the packing fill's width and colour; "—" in empty cells |
| Page: selection | `test_browse_page.py` | A row click checks it and draws the bar; the header checkbox checks every visible row; the bar's checkbox clears; Open with one, Export with two; double-click and Enter call `openSession` |
| Page: Status and Comment | `test_browse_page.py` | The menu's title and four items; an item calls `setStatus` with the checked names; the popover's title, note and prefill for one and several; Save calls `setComment` with the trimmed text; Cancel and Escape close without a call; a state push keeps the draft |
| Page: footer | `test_browse_page.py` | The archived line only on All with archived rows; Show adds them and reads Hide |
| Page: toast | `test_browse_page.py` | An undoable toast shows Undo, which calls `undo`; a plain one does not; dismiss hides it |
| Widget: loading | `test_session_browser_reload.py` (adapted), `test_session_browser_widget.py` (new) | The hidden-load retry and the client-switch rules as today; a loud refresh pushes `loading`; a load error pushes `failed`; a client change empties the rows; a quiet refresh keeps them |
| Widget: writes | `test_session_browser_widget.py` | Status and comment reach `SessionManager` for every named entry with `manual=True`; an unknown name is ignored; the toast texts; one failure in three shows the banner and still toasts for two; open and export emit paths |
| Widget: Undo | `test_session_browser_widget.py` | On a real `SessionManager` in `tmp_path`: archive two sessions then Undo restores status, the hand-set flag and `status_updated_at`; a comment then Undo restores the comment and `last_updated`; a second Undo does nothing |
| Lifecycle sync | `test_session_browser_lifecycle_sync.py` | Unchanged: it tests the worker |
| Shell | `test_shell.py` | Tab 2 holds a `QWebEngineView`; the inset is 0 on Browse and 5 on Logs |
| Toast router | `test_toast_router.py` | On Browse a toast reaches `session_browser.bridge` and no Qt toast shows; the Qt case moves to Logs |
| Open | `tests/audit/test_05_sessions_sweep.py` | Opening a session with no analysis lands on Setup |
| Shortcuts | `test_shortcuts_dialog.py` | Passes with the F5 row: the window binds it |
| Lint | `test_style_literals_guard.py` | Unchanged: `gui/` scans clean with the three new assets |

Every other test that pins what this spec changes is rewritten to the new behaviour in the same commit as the
change, never skipped.

**Visual check (required, CLAUDE.md):** render the page through `QWebEngineView.grab()` at 1166×720, in light
and dark, in each state: default list, two checked, the Status menu, the Comment popover, no match, loading,
no client, no sessions, failed, archived shown. Render `MainWindow` on Browse in both themes. Compare with
`mockups/renders/browse.png` and the mockup's other states opened in Chrome. Save the light default, the dark
Status menu, the light Comment popover and the light loading under `docs/design/ui-refresh/renders/phase4/`
and attach them to the PR.

**Gate:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check .`, then
`graphify update .`.

## 11. Docs

- `CONTEXT.md`:
  - **Web tier**: Results, Setup and Browse today.
  - **Selection bar**: the Browse page has one too; the Qt one is gone.
  - **Badge**: a session's badge carries a dot whose fill says how far the session has come: hollow, half,
    solid.
  - **Shape**: no screen of this app draws it now; the session row's badge dot took its place.
  - Add **Browse state**: the map Python builds for the Browse page: the view and one record per session.
    The page filters and groups it and decides no fact.
  - Add **Needs attention**: the group of sessions that are paused, stale, incomplete, or in flight with
    blocked orders. (**Display status** is already defined.)
  - **Qt tier**: everything except the screens that have moved to the web tier.
- ADR 0016, Consequences: `BrowseBridge` is the third bridge; a third view, on the phase 3 measurement.
- `docs/design/ui-refresh/roadmap.md`: phase 4 gets its spec and plan paths and the differences from its
  list (Export stays, no sorting, the countdown in the tooltip, Undo restores timestamps, the chip stays in
  the bar).
- `.github/workflows/build_release.yml`: the bundle check also looks for `browse.html`.

## 12. Out of scope

- Ctrl+F on Browse (it still goes to Results' search). Sorting. Row virtualisation. Moving the writes off
  the GUI thread.
- A longer toast for Undo. Tools, Logs, Client settings. Packing Tool. Anything in `shared/`.

## 13. Delivery

One PR on `cognitiveghost/shopify-fulfillment-tool` from `dr/16-ui-refresh-phase-4-move-browse-to-the-we`.
No Packing Tool PR: nothing in `shared/` changes.
