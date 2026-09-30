# Claude Design prompt pack — Fulfilment Tool UI refresh

Prompts for Claude Design, one per screen, built from [`audit.md`](audit.md). Their output is a set of
mockups the owner approves. After approval, each mockup is the brief for its own implementation task
(CLAUDE.md: "the mockup is the brief").

## How to use

1. Start one Claude Design project named **Fulfilment Tool — UI refresh**.
2. Paste **§0 Style brief** as the first message. Attach `current/light-results.png` and
   `current/light-setup.png`.
3. Then send one screen prompt per turn, §1 to §7 in order, attaching the screenshots each one lists.
   §1 (Shell) goes first because every later screen sits inside it.
4. Ask for changes in the same turn's thread. When a screen is right, export it and save it as
   `docs/design/ui-refresh/mockups/<screen>.html` (e.g. `setup.html`), linked from a new task.

Each prompt stands on its own after §0, so a screen can be redone without replaying the others.

---

## §0 Style brief (paste once, first)

> You are designing the next version of **Fulfilment Tool**, a Windows desktop app that warehouse
> supervisors use to turn a Shopify orders export and a stock export into a picking plan: which orders
> ship today, which are blocked and why, and the packing lists, labels and stock write-offs that
> follow. One supervisor works on one client (a shop) at a time, usually over Remote Desktop at
> **1366×768**, sometimes at 1920×1080. They use it all shift, so density and scanning speed matter
> more than whitespace.
>
> **Visual direction: the current Shopify admin (Polaris design language), rebuilt, not imported.**
> Match its look and feel: a light neutral-grey canvas; white content cards with ~12px radius and a
> soft, low shadow; compact 13px body text; semibold 14px card titles; a page header with the title
> on the left and actions on the right; a **near-black primary button** with white text; plain
> secondary buttons with a hairline border; tinted pill **badges** by tone (success, critical,
> warning, info, neutral); index tables with a checkbox column, a bold identifier column, row hover
> and a bulk-action bar that replaces the header while rows are selected. Do not use Shopify's logo,
> icons, illustrations, or the name "Shopify" in the UI chrome. Icons are Lucide, stroke 1.5.
>
> **Hard constraints (the build depends on them):**
> - Two layers. The **shell** (left navigation, top command bar, bottom status line) is drawn by Qt
>   widgets: flat only, borders and background planes, **no shadows**. The **screen content** inside
>   the shell is HTML/CSS in an embedded Chromium: shadows are allowed there.
> - No gradients, no transitions or animation, no transforms, no opacity fades, anywhere. State
>   changes are instant.
> - Fonts: **Segoe UI** for text and **Consolas** for SKUs, order numbers and times. No web fonts:
>   the app runs offline.
> - Deliver **light and dark** themes for every screen. Polaris has no dark mode, so derive one:
>   same structure, near-black canvas, cards one step lighter than the canvas, shadows replaced by a
>   1px border in dark.
> - Name colours as tokens, not hex. Use these existing names and propose values for them:
>   `surface_sunken` (canvas), `surface` (card), `surface_raised`, `surface_overlay`, `text`,
>   `text_secondary`, `text_disabled`, `text_placeholder`, `border`, `border_subtle`,
>   `border_strong`, `status_info/_bg`, `status_success/_bg`, `status_warning/_bg`,
>   `status_danger/_bg`, `accent_fill/_hover/_active`, `on_accent`, `selection_border`,
>   `selection_bg`, `focus_ring`. If a design needs a new token (e.g. `card_shadow`), name it and say
>   why.
> - Disabled controls must look disabled at a glance, not just have lighter text.
> - Every screen shows its states: default with realistic data, empty, working (a named step, not a
>   spinner or shimmer), and failed.
>
> **Vocabulary (use these words exactly):** *client*, *session*, *order line*, *SKU line*,
> *Fulfillable*, *Blocked* (never "Not fulfillable" or "Short on stock"), *repeat order*, *stock left*,
> *lot*, *packing list*, *stock export*, *courier label*. Messages follow four routes: a **toast** for
> something that worked (with Undo where possible), an **inline message** next to the field that has a
> problem, a **confirm** only before destroying data Undo cannot reach, and an **error banner** for a
> failure. Empty states name the cause, name the file or filter that caused it, and offer the one
> action that fixes it. No apologies, no exclamation marks.
>
> Output: one HTML page per screen, with a light/dark toggle and a state switcher, sized to
> 1366×768 first. Reply to this message with the token values and a one-screen component sheet
> (buttons, badges, card, table row, input, segmented control, empty state, toast), then wait for the
> first screen prompt.

---

## §1 Shell — navigation, command bar, status line

Attach: `current/light-setup.png`, `current/light-setup-no-client.png`.

> Design the **shell** every screen sits in. Qt draws it, so it is flat (no shadows).
>
> **Left navigation.** Five destinations, in this order, each with a Lucide icon: **Setup**
> (clipboard-list), **Results** (table), **Browse** (folder-open), **Logs** (info), **Tools**
> (wrench). Shortcuts Ctrl+1…5. Today it is a 56px icon rail with tiny labels and a barely visible
> active state (see screenshot). Propose a Shopify-admin-style sidebar: ~200px with icon + label, a
> clear active item, the app mark ("Fulfilment Tool") at the top, and **Client settings** and the
> **Light/Dark** choice pinned at the bottom. It must collapse to an icon-only 56px rail (a toggle,
> remembered per PC), because 1366px is tight. Results is disabled until a session has been analysed.
>
> **Top command bar**, one row:
> - Left: the **client selector**, a combo showing the client name with a coloured dot for the
>   server connection. Its dropdown lists clients grouped by client group, then three actions:
>   Refresh clients, New client…, Manage groups…. With no client it must say "Choose a client".
> - Then **New session** and **Open recent ▾** (the last sessions of this client).
> - Right: the current screen's **one primary action**, mirrored from the screen (e.g. *Run analysis*
>   on Setup, *Export N orders* on Results), then a `…` overflow holding Client settings…, Server
>   connection…, and the theme choice. If the sidebar takes over settings and theme, say what is
>   left in the overflow.
>
> **Status line.** Today a full-width bar shows only "Server connected". Keep the connection
> state (connected / reconnecting / unreachable with the server path) but find it a smaller home.
> The sidebar footer or the command bar's right edge are both fine.
>
> Show: no client chosen; client chosen with no session; session open; analysis running (the primary
> becomes a disabled "Running…" and the named step shows); server unreachable.

---

## §2 Setup

Attach: `current/light-setup.png`, `current/light-setup-no-client.png`.

> Design **Setup**, where a supervisor starts a session for the chosen client and runs the analysis.
> Page title "New session"; the session name (`2026-09-30_1`) appears once one exists.
>
> Content today (keep all of it):
> - **Orders file**: a drop zone for the Shopify orders export (CSV), with *Choose file…* and
>   *Choose folder…* (a folder merges every CSV in it into one input). Once loaded it shows the file
>   name, row count, order count, detected delimiter, and a *Replace* action. Folder merges list
>   their files.
> - **Stock file**: the same, for the warehouse stock export.
> - **Inventory memory**: a switch. On means this run starts from the stock left by the client's
>   previous run instead of the stock file's numbers. Say that in one line under the switch.
> - **Allocation strategy**: two choices, *Multi-item first* ("Fills orders that can go out whole
>   before partial ones. A few old orders wait longer for stock instead.") and *Oldest first*
>   ("Fills strictly by order date, whatever it contains. No order waits behind a newer one; more
>   leave part-filled."). Keep these texts.
> - **Run analysis**, the page's primary action, enabled only when both files are valid.
>
> Today this is a narrow centred form inside a card inside a card, and the page's primary action is
> not visible until both files load (see screenshot). Use the width: e.g. the two file cards side
> by side, and a right-hand or bottom **Run summary** card that says what will happen ("312 orders,
> 1,204 lines, stock for 188 SKUs, multi-item first") with the primary action in it.
>
> States: no client (an empty state: "Choose a client to begin — Pick a client in the bar above.
> Sessions, stock and reports all belong to one client."); no files yet; orders loaded, stock missing;
> a file with a problem (an inline message under that file card, e.g. "No SKU column — the orders
> file's header row has no column mapped to SKU. Open Orders Mapping"); both loaded and ready; running
> with a named step ("Allocating stock — 140 of 312 orders"); server unreachable.

---

## §3 Results

Attach: `current/light-results.png`, `current/dark-results.png`.

> Restyle **Results**, the screen after an analysis. It is already HTML and already the app's best
> screen, so **keep its information and behaviour exactly** and move it onto the Polaris look.
>
> What is there: a **KPI strip** (Orders, with lines and SKUs touched; Fulfillable, with % of
> orders; Blocked, with lines and SKUs; Labels, split by courier "DHL 10 · DPD 10 · Speedy 10";
> Value ready, which says "No price column mapped" when there is no price column); a **filter bar**
> (search "Order, customer or SKU", *Add filter*, a count "40 orders", *Columns 9/18* which opens the
> column manager, a `…` overflow, and the primary **Export 30 orders**); an **index table** (checkbox,
> Status chip, Order in Consolas, Customer, Lines, Units, Value, Courier, Age like "19 h", Repeat);
> and a **detail pane** on the right that shows the selected order: a one-sentence verdict ("Ships
> complete" or "Blocked: CRM-50ML short by 2"), its reason codes, its SKU lines with stock left and
> lot (expiry, batch), and per-order actions (*Hold* or *Mark fulfillable*, exclude the order, remove a line). ↑/↓
> moves through orders.
>
> Selecting rows swaps the table header for a **selection bar** (count, *Mark 3 fulfillable*, *Hold
> these 3*, and a *More* menu: add/remove a tag, copy order numbers, export to Excel or CSV, remove a
> SKU from these orders, remove whole orders containing a SKU). The destructive ones open a **bulk
> popover** that says what will change before it does. Toasts appear inside this page, bottom right, with Undo.
>
> Fix these from the audit: the table and the detail pane should share one surface rule (both
> cards, or a split card); *Value ready* should not spend a fifth of the strip saying it is
> unavailable (fold it into a hint); the pane's lone collapse chevron needs a header.
>
> States: default (40 orders, 10 blocked); one order selected; three selected with the selection
> bar; the bulk popover open; a filter that matches nothing ("No orders match — Status is Blocked
> and Courier is DPD. Clear filters"); a toast with Undo.

---

## §4 Browse

Attach: `current/light-browse-no-client.png`, `current/dark-browse-no-client.png`.

> Design **Browse**, the list of this client's sessions on the file server.
>
> Each session row has: **Session** (name like `2026-09-30_1`, Consolas), **Age** ("3 d"),
> **Status**, **Orders**, **Items**, **Blocked**, **Packing** (packing progress from the separate
> Packing Tool, e.g. "142 / 188"), **Comment**. Status is one of eight display statuses: not started,
> in progress, paused, stale (untouched 7 days), completed, incomplete, abandoned, archived. A person
> can set four of them (Active, Completed, Abandoned, Archived). Sessions fall into two groups,
> **Needs attention** (paused, stale, incomplete, or still in flight with blocked orders) and **Everything else**, each with a
> count.
>
> Toolbar: search sessions, a count, a status filter (All, Active, Completed, Abandoned, Archived),
> Refresh. Archived sessions are hidden unless asked for; a footer says "12 archived · Show".
> Selecting rows shows a selection bar with *Status ▾* and *Comment…*. Double-click or *Open* opens
> the session in Setup/Results.
>
> Use the Polaris index-table pattern with status badges. Consider a top row of **tabs** (All,
> Active, Completed, Abandoned, Archived) in place of the status combo, as Shopify's Orders page does.
>
> States: 25 sessions, 4 needing attention; no client ("Choose a client — Pick a client in the bar above
> to see its sessions."); client with no sessions ("No sessions yet — ACME has no sessions on the
> file server." + *New session*); a search that matches nothing; loading ("Reading sessions from
> the server…"); two rows selected.

---

## §5 Logs

Attach: `current/light-logs.png`, `current/dark-logs.png`.

> Design **Logs**, the log viewer. Each entry has time (Consolas), level (Info, Warning, Error),
> source and message. Two sources: **Activity** (what the supervisor did) and **Execution** (what
> the app did). Filters: source, level (All, Info, Warning, Error), a search box. Options: *Wrap*
> long messages and *Follow* the newest entry (on only while scrolled to the bottom). Action: *Save
> as text*.
>
> Today the two filter groups are loose outlined buttons (see screenshot). Make them real segmented
> controls, give levels a badge tone (Warning = warning, Error = critical), show only the last segment
> of a module source (`main_window_pyside` rather than `gui.main_window_pys…`), and keep the table
> dense. It is a log, so no row cards.
>
> States: 200 mixed entries; filtered to Errors; a search with no matches; an Error entry expanded
> to show a multi-line traceback.

---

## §6 Tools

Attach: `current/light-tools.png`.

> Design **Tools**, two label utilities that work on the open session.
>
> **Reference labels** stamps each courier label PDF with its order's reference number. Inputs:
> *Labels PDF*, *Mapping CSV*, output folder (defaults to the session's folder, *Change…*), "Open
> the PDF when it's ready". Actions: *Process labels* (primary), *Print…*.
>
> **Barcode labels** makes one barcode label for every Fulfillable order in a packing list, each list
> in its own folder. Inputs: *Packing list* (a combo of this session's packing lists, with Refresh),
> output folder, "Add QR labels (order number)", "Open the PDF when it's ready". Actions: *Generate
> barcode labels* (primary), *Print…*, *Print QR labels…*.
>
> Both tools print in one of two **print modes**, set per tool and per PC: through the Windows print
> dialog (*Driver*) or as raw ZPL sent straight to a label printer (*Raw ZPL*, with a printer target).
> Today this hides behind a sentence-long disclosure. Make it a visible setting.
>
> Today each tool is a card inside a card, "No session selected" appears twice, and every button has
> the same weight (see screenshot). One card per tool, one primary each, and one "Open a session to
> use these tools" state for the page, not per field.
>
> States: no session open; session open and ready; generating ("Writing labels — 40 of 120"); done
> (toast: "120 labels saved to …\Barcodes\DHL" with *Open folder*); a mapping CSV with a problem
> (inline message).

---

## §7 Client settings

Attach: `current/light-settings-general.png`, `current/light-settings-rules.png`.

> Design the **Client settings** window, a large modal (or a full page, if you argue for it) that
> configures one client. Left: a search box and a grouped nav: **Data** (General, Orders Mapping,
> Stock Mapping), **Fulfillment Logic** (Rules, Sets, Weight), **Output** (Reports),
> **Organization** (Tag Categories). Right: the page. Footer: *Save* (primary) and *Cancel*; pages
> with unsaved changes are marked in the nav.
>
> Pages, briefly:
> - **General**: stock and orders CSV delimiter (Auto — detect per file, or a character), low-stock
>   threshold.
> - **Orders Mapping** / **Stock Mapping**: map each internal field (Order number, SKU, Quantity,
>   Courier, Customer, Created at, …) to a column of the client's CSV; courier name mappings;
>   *additional columns* (unmapped CSV columns kept for Results).
> - **Rules**: a list of rules, each "when *conditions* then *actions*" (e.g. when Tags contains
>   "VIP" then add the internal tag "priority"), with add, filter by name, reorder, enable/disable, and a *Test rule*
>   dialog that runs a rule against the current analysis.
> - **Sets**: set/bundle SKUs and the component SKUs each one decodes into.
> - **Weight**: volumetric weight settings, read from the stock file's columns.
> - **Reports**: packing list and stock export definitions (name, filters, columns).
> - **Tag Categories**: tag groups with colours used across Results.
>
> Today pages share no anatomy: General has a heading, Rules has none, and Rules with no rules is an
> empty white box with "No rules defined" in a corner (see screenshots). Give every page the same
> header (title, one-line description, page actions on the right) and group its content into cards
> with section titles, Polaris settings-page style. Fields are sized to their content, not the
> window.
>
> Mock at least: General; Rules with three rules; Rules empty ("No rules yet — Rules change orders
> after the analysis, e.g. tag VIP orders. Add rule"); Orders Mapping with one unmapped required
> field (inline message); the nav with an unsaved page.
