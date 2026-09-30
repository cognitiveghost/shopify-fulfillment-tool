# UI audit — Fulfilment Tool, 2026-09-30

What every destination looks like today, and what is wrong with it. This is the input to the Claude
Design prompt pack in [`prompts.md`](prompts.md); the screenshots it cites are in [`current/`](current/).

**How the renders were made.** `QT_QPA_PLATFORM=offscreen`, `MainWindow` at 1366×768 (the smallest
RDP session the warehouse runs), against a throwaway server with one client (`ACME`) and 40 synthetic
orders pushed into Results. Offscreen Qt uses a fallback font, not Segoe UI, so glyph widths differ a
little from Windows. Layout and spacing do not.

Severity: **Bug** is wrong behaviour and gets fixed in this task. **Major** hurts every session.
**Minor** is polish.

## Across the whole app

| # | Sev | Finding |
|---|-----|---------|
| A1 | Major | **Two design languages.** Results (web tier) reads as a modern admin screen, with a KPI strip, a real table, chips and a detail pane. Every Qt screen reads as a settings form. Moving between Setup and Results feels like changing apps. |
| A2 | Major | **No page structure.** No screen has a page title, subtitle or header actions row. The only title-like text is the command bar's client selector. Polaris's page header (title, then primary and secondary actions on the right) is missing everywhere. |
| A3 | Major | **Wasted canvas at 1366×768.** Setup uses a 840px centred card and leaves ~40% of the width empty; Tools stops at ~410px tall and leaves the lower half blank; Browse's empty state floats in a sea of grey. |
| A4 | Major | **Cards are used three different ways.** Setup is one sunken card with a white card inside it, Tools is two sunken cards each with a white card inside, Browse and Logs have no cards. There is no rule for when content sits on a card. |
| A5 | Minor | **The rail is weak.** 56px wide with small labels, and an active state that is only a slightly darker tile. No app mark at the top, and nothing at the bottom (settings and theme live in the command bar's `…` overflow). |
| A6 | Minor | **Disabled buttons look enabled.** Tools' `Print…`, `Process Labels` and `Generate Barcode Labels` are disabled (no session), but only their text is a shade lighter. |
| A7 | Minor | **The status bar carries one fact.** A full-width bar exists to show `Server connected` in the right corner. |

## Shell — rail, command bar, status bar

Screenshots: every `current/*.png` except the settings pair.

- The command bar holds the client selector (a combo with a connection-coloured dot), `New Session`,
  `Open recent ▾` and a right-hand `…` overflow. With no client the selector is an empty grey box with
  no placeholder (`current/light-setup-no-client.png`).
- `Open recent` draws its caret glyph below the baseline (`Open recent⌄`).
- The screen's primary action (e.g. `Run analysis`) is mirrored into the command bar
  (`_SCREEN_ACTIONS`, `gui/ui_manager.py:44`), but on Setup it is not visible until both files are
  loaded, so a first-time user sees no primary action at all.

## Setup (`current/light-setup.png`, `current/light-setup-no-client.png`)

- **Bug S1 — clipped empty state.** "Choose a client to begin" cuts its second sentence in half. The
  cause is in `shared/components/state_panel.py`: the card is centred with `Qt.AlignCenter`, so the
  layout sizes it from `sizeHint()` and never asks the wrapped label's `heightForWidth()`. Any
  `StatePanel` whose cause wraps is clipped, in both apps. Fixed in this task.
- The form is a two-column label/field grid inside a nested card. Labels (`Orders file`, `Stock file`)
  are top-aligned with 90px-tall drop zones, so they float.
- Allocation's radio cards use heading-size bold titles, larger than anything else on the screen, and the radio
  dot does not line up with the title.
- `Use Inventory Memory` is a bare checkbox with no explanation of what it does. The term is defined in
  `CONTEXT.md` and the screen never uses it.

## Results (`current/light-results.png`, `current/dark-results.png`)

The strongest screen, and the reference for the rest.

- The KPI strip, filter bar, table, chips and detail pane are right. Keep their information and
  behaviour.
- The table sits directly on the canvas while the detail pane is a grey card. The two halves do not
  share a surface rule.
- `Value ready —` is a KPI whose only content is "No price column mapped". A placeholder that permanent
  should be an inline hint, not a fifth of the strip.
- The detail pane's collapse chevron floats alone in the top-right corner.

## Browse (`current/light-browse-no-client.png`, `current/dark-browse-no-client.png`)

- **Bug B1 — `CLIENT_None`.** With no client selected the empty state says "CLIENT_None has no sessions
  on the file server" and offers `New session`, which cannot work without a client
  (`SessionBrowserWidget._empty_reason`). Fixed in this task.
- The toolbar is a full-width search box, a `0 sessions` count, a status combo and `Refresh`, which
  takes three different visual weights for four controls.
- Rows (not rendered here: the throwaway server has no sessions) are a `QTreeWidget` with eight columns
  (Session, Age, Status, Orders, Items, Blocked, Packing, Comment), status shapes drawn by
  `session_row_delegates.py`, a selection bar with `Status ▾` and `Comment…`, and an
  `N archived · Show` footer.

## Logs (`current/light-logs.png`, `current/dark-logs.png`)

- Two segmented groups (`Activity | Execution`, `All | Info | Warning | Error`) are drawn as separate
  outlined buttons, so they do not read as segmented controls.
- The table has no card, no row separators and no zebra, which is fine for logs. `SOURCE` elides module
  paths (`gui.main_window_pys…`) where the last segment is the only useful part.
- `Wrap` and `Save as text` sit on the far right with no grouping.

## Tools (`current/light-tools.png`)

- Two tool cards side by side, each with a white form card nested inside a grey card. The nesting
  carries no meaning.
- `No session selected` appears twice per card (once as field text, once as a status line).
- Three to four buttons per card in the footer, all the same weight. There is no primary.
- The disclosure `▸ Prints through the print dialog…` hides print mode behind a sentence.

## Client Settings window (`current/light-settings-general.png`, `current/light-settings-rules.png`)

- A modal with a search box, a grouped left nav (Data, Fulfillment Logic, Output, Organization) and a
  page on the right. The structure is right.
- **Pages have no shared anatomy.** General has a heading `General Settings`; Rules has none. Rules
  starts with a toolbar, General with a form.
- Rules with no rules is an empty white box with "No rules defined" in the top-right corner. That is
  the "No data" case `StatePanel` exists to replace.
- General's delimiter combos are stretched to 830px for a value that is at most 20 characters.

## What the redesign should keep

- The information architecture: five destinations, one client at a time, one primary action per screen.
- Everything Results already does (see `CONTEXT.md` § Results for the vocabulary).
- Status chips (outlined pill + mark), the selection ring, the selection bar, toasts, the state-panel
  rule ("name the cause, name the file, offer the action").
- Both themes. Segoe UI for text, Consolas for SKUs and order numbers.
