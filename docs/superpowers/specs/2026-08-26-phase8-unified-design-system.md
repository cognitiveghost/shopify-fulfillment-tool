# Phase 8 — Unified design system (Parcker × Depot)

**Date:** 2026-08-26
**Status:** design contract. Supersedes and replaces the 2026-08-25 Phase 8 docs
(`phase8-redesign-scope`, `phase8.1-design-system-design`, `phase8.1-navigation-map`),
which were deleted in the same commit — the mockups below replace the token tables and
the navigation map those documents carried.

**Sources — both are canonical, this document is their merge:**

| | project | covers |
|---|---|---|
| **Parcker** `dff39e7a-a628-4731-8a2b-3f7641cbe4dc` | *Parcker Design System v0.9* | the universal spec: colour roles, status semantics, type, density, 6 component groups, Packer Mode / Session Browser / dialogs / migration table. Packing-Tool-facing. |
| **Depot** `141e30eb-c0dd-4c0a-8799-44d65aa7cf9b` | *Fulfillment System v1* | the applied screens: shell (rail + command bar), Analysis Results in three directions (1a/1b/1c), Session Setup (1d), Session Browser (1e), Tools (1f). Shopify-Tool-facing. |

They are one system at two densities, not two systems. Parcker names the vocabulary;
Depot exercises it on real screens. Where they disagree, §2 records the resolution.

---

## 1. Already shipped — do not rebuild

Verified against `origin/main` @ `56e3553` on 2026-08-26. **PR #294 merged the Phase 8.2
token expansion**, so most of Parcker's colour table is already live in `shared/theme.py`:

- Four-plus token families present and contrast-validated: `surface` / `surface_raised` /
  `surface_overlay`, `text` ×4, `border` / `_subtle` / `_strong`, all eight `status_*`
  (+`_bg`), `accent_fill`, `on_accent`, `selection_bg` / `selection_border`, `focus_ring`,
  `hover`.
- Scales present: `radius_sm/md/lg` = 3/6/10, `spacing_xs…2xl` = 4/8/12/16/24/32.
- The ten legacy names (`background`, `background_elevated`, four `accent_*`,
  `active_background`, `active_border`, `button_hover_light/dark`) are retained as
  aliases — ~180 call sites read them by exact attribute name. Parcker calls these
  "frozen migration shims"; that is exactly what they are. **No new call site may read
  one.**
- `tests/test_theme_contrast.py` guards the synced result.
- A type scale already exists in `gui/theme_manager.py` (`TYPE_SCALE`, `font_css`,
  `apply_font`): caption 9 / body 10 / label 12 / heading 14 / display 17, all in points.
- Shopify Tool already has `gui/assets/` — Inter Regular+Bold and 17 Lucide SVGs.

**Consequence for the roadmap:** the old plan's 8.2 is *done*, not aborted. What remains
is a small delta (§3), not a rewrite.

---

## 2. The four conflicts, resolved

### C1 — Surface planes: Parcker has three, Depot has four

Depot introduces `surface_sunken` for the app frame, the 56 px rail and gutters, and
lightens the page plane so it reads *above* the frame without a border. This is what
delivers Depot's fault #1 ("everything is outlined — a 1 px border on every widget"):
regions separate by elevation, and borders are reserved for inputs and the one focused
control.

**Resolved: adopt Depot's four planes, keep Parcker's names.** It is a superset; nothing
Parcker specifies is lost.

| token | light | dark | role |
|---|---|---|---|
| `surface_sunken` | `#E8E8EB` | `#08080B` | **NEW** — app frame, nav rail, gutters |
| `surface` | `#FFFFFF` | `#101014` | page background, table body, dialog ground — **dark value changes from `#0A0A0A`** |
| `surface_raised` | `#F4F4F5` | `#17171B` | panels, cards, toolbars, status bar |
| `surface_overlay` | `#EAEAEC` | `#202027` | inputs, menus, combo popups, hover |

Light elevation runs *downward* in luminance (`surface` is the lightest) — that is how the
shipped light theme already works, and `surface_sunken` continues the ramp. Do not
"correct" it.

**Measured before proposing** (2026-08-26) — moving dark `surface` `#0A0A0A` → `#101014`
costs every foreground 0.2–0.4 of ratio and **every token still clears its floor**:

| token | floor | on `#0A0A0A` | on `#101014` |
|---|---|---|---|
| `text` | 7.0 | 17.68 | 16.96 |
| `text_secondary` | 4.5 | 9.13 | 8.75 |
| `text_placeholder` | 4.5 | 5.73 | 5.50 |
| `text_disabled` | 3.0 | 3.88 | 3.72 |
| `status_info` | 4.5 | 5.75 | 5.52 |
| `status_success` | 4.5 | 7.12 | 6.83 |
| `status_warning` | 4.5 | 9.19 | 8.81 |
| `status_danger` | 4.5 | 5.70 | 5.47 |

`text` on `surface_sunken #08080B` = 17.87; `text_secondary` = 9.22. Both clear.

**Amended 2026-08-26 — light `surface_sunken` was asserted, not measured.** The table above
only measured *dark* `surface_sunken`. Measuring the light value revealed the gap: light's
existing tokens were tuned to exactly clear `surface_overlay #EAEAEC`, which the code
comment in `shared/theme.py` already names as light's binding plane — `text_placeholder`
lands there at 4.50 and `status_info` at 4.52. Adding a plane one step *darker* than the
old darkest necessarily costs ratio, because in light theme the background is the lighter
side of `(L_lighter + 0.05) / (L_darker + 0.05)`. Six shipped tokens fall short against
`#E8E8EB`, all by 0.02–0.08:

| token | value | on `#EAEAEC` | on `#E8E8EB` | floor |
|---|---|---|---|---|
| `text_placeholder` | `#6A6A6A` | 4.50 | 4.42 | 4.5 |
| `border` | `#868686` | 3.03 | 2.98 | 3.0 |
| `status_info` | `#006DB7` | 4.52 | 4.44 | 4.5 |
| `status_success` | `#347736` | 4.55 | 4.47 | 4.5 |
| `status_warning` | `#995B00` | 4.54 | 4.46 | 4.5 |
| `status_danger` | `#D0190B` | 4.57 | 4.49 | 4.5 |

**Resolved: `surface_sunken` keeps `#E8E8EB`; the six foregrounds widen to meet it.** The
ramp's premise — sunken is the darkest plane — is load-bearing for 8.6's nav rail and every
later phase, so the plane does not move. Each foreground darkens by the minimum that clears
its floor, one to two sRGB units per channel:

| token | from | to | on `#E8E8EB` | floor |
|---|---|---|---|---|
| `text_placeholder` | `#6A6A6A` | `#686868` | 4.56 | 4.5 |
| `border` | `#868686` | `#858585` | 3.02 | 3.0 |
| `status_info` | `#006DB7` | `#006BB5` | 4.55 | 4.5 |
| `status_success` | `#347736` | `#337635` | 4.54 | 4.5 |
| `status_warning` | `#995B00` | `#985A00` | 4.52 | 4.5 |
| `status_danger` | `#D0190B` | `#CF180A` | 4.53 | 4.5 |

Verified: `validate_theme` passes on both themes with these values and the four planes in
place. Every other light foreground already clears `#E8E8EB` with room — `text` 14.23,
`text_secondary` 5.64, `text_disabled` 3.23, `focus_ring` 5.03, `selection_border` 4.44.

Two consequences worth stating so a later phase does not "fix" them:

- `accent_green` / `accent_orange` / `accent_red` are aliases of `status_success` /
  `status_warning` / `status_danger`. The alias-drift check requires them to carry the same
  value, so they move in lockstep. This changes their *value*, not what they point at, so
  the "legacy aliases are read-only until 8.3" rule still holds.
- `selection_border` and `active_border` merely *happen* to share `#006DB7` with
  `status_info`; they are not aliased to it. They stay at `#006DB7` and now differ from
  `status_info` by two units — invisible, and `selection_border` clears its 3.0 floor at
  4.44 either way.

Two alternatives were measured and rejected. Letting `surface_sunken` rise to or above
`surface_overlay` clears the floor but inverts the token's name, and every later phase reads
the ramp as ordered. Exempting the six tokens from the `surface_sunken` pairing keeps every
hex as shipped, but writes an exemption list into the one check whose stated purpose is that
no pairing goes unmeasured — and 8.6 puts the nav rail on `surface_sunken`, where status
colours land and the exemption would still be active.

### C2 — Type scale: Parcker proposes seven rungs, Depot proposes six, five already ship

Parcker (floor-facing) wants display 22 / title 18 / heading 16 / subheading 13.
Depot (desk-facing) wants display_xl 28 / display 17 / title 15 / label 12.
Shipped: caption 9 / body 10 / label 12 / heading 14 / display 17.

Most of the divergence is 1–2 pt noise, not design: Depot's "title 15, panel headers" and
the shipped "heading 14, dialog and section headers" are the same rung.

**Resolved: keep the five shipped rungs, add exactly one.**

| rung | pt | weight | use |
|---|---|---|---|
| `caption` | 9 | regular | chips, meta lines, uppercase column heads |
| `body` | 10 | regular | default — controls, table cells, buttons |
| `label` | 12 | bold | emphasis, sub-headers, count badges |
| `heading` | 14 | bold | panel, section and dialog headers *(absorbs Depot `title`, Parcker `title`/`heading`)* |
| `display` | 17 | bold | stat-card numbers, section totals |
| `display_xl` | 28 | bold | **NEW** — KPI numerals only, and Packer Mode's scan verdict |

`display_xl` is the one genuinely new rung, and it is justified twice: Depot's fault #2
("the scale tops out at 17 pt, so a 23-column table and a section title carry the same
weight") and Parcker's requirement for a verdict readable across an aisle. Parcker asked
for 22 pt; 28 pt serves that better and costs no extra rung.

Two rules both sources agree on, neither yet implemented:

- **Points everywhere.** Widget code mixes `13px` panel headers with `18pt` dialog titles,
  so nothing scales together when Windows DPI changes.
- **Mono is load-bearing.** SKUs, session IDs, barcodes and PC names use
  `font_family_mono` so `O`/`0` and `l`/`1` stay separable when read aloud. The token
  exists; no widget uses it.
- **`font-variant-numeric: tabular-nums`** on every numeral column (Depot), so quantities
  and stock align down the column.

### C3 — Density: different numbers, and a direct contradiction on type

Parcker: compact (opt-in) row 24 / control 26; comfortable (default) row 32 / control 34;
and *"density changes control height and padding only — never type size"*.
Depot: desk 32 (default) / floor 44, and floor **does** raise body 13.3 → 16 px.

**Resolved:**

- Two profiles named **desk** and **floor**. Depot's control heights win — 34 px is thin
  for gloves and 44 px is the standard touch target.
- **The default is per-app, not global.** Shopify Tool defaults to `desk` (a supervisor
  with a mouse); Packing Tool defaults to `floor` (Parcker: *"a station that has not been
  told otherwise is a scan station"*). One flag, two defaults — neither source loses.
- Parcker's "never type size" rule is **deliberately overridden in one place**: floor
  raises `body` 10 → 12 pt and `caption` 9 → 10 pt. Nothing else moves. Reason: at arm's
  length a 10 pt body is the failure, and holding the rule would mean shipping a scale
  nobody on the floor can read. Record it as an exception, not a silent drift.

| | control | row | padding | body / caption |
|---|---|---|---|---|
| **desk** | 32 | 28 | `spacing_xs` / `spacing_sm` | 10 / 9 |
| **floor** | 44 | 40 | `spacing_sm` / `spacing_md` | 12 / 10 |

Colour and radius never change with density.

### C4 — The shipped AA failure (Parcker's "FIX FIRST")

**Confirmed by measurement, and it is on `main` today.** `DARK_THEME.button_hover_dark =
#2D9FE8` sits behind white label text at **2.90:1** — below the 4.5:1 floor. It survived
review because `validate_theme` proves `on_accent` against `accent_fill` **only**;
`QPushButton:hover` and `:pressed` swap a different fill in behind the same white text and
nothing measures it. `shared/theme.py:309` already carries a `ponytail:` comment naming
this exact gap, so it is tracked debt, not a surprise — Parcker found it independently.

**Resolved: adopt Parcker's fix verbatim.** Two theme-independent tokens — a button fill
sits on itself, not on a surface, so it needs no per-theme value:

| token | value | white on it |
|---|---|---|
| `accent_fill` | `#006FBA` | 5.27:1 |
| `accent_fill_hover` | `#0A78C4` | **4.67:1** |
| `accent_fill_active` | `#005A9E` | **7.10:1** |

`button_hover_light` / `button_hover_dark` are re-pointed at these and join the frozen
alias list. They already carried identical values within each theme, so nothing is lost.

**The class fix, which matters more than the two hexes:** `validate_theme` must loop the
`on_accent` assertion over **fill, hover and active** rather than fill alone. That is how
the 2.90:1 shipped, and looping closes the class permanently.

---

## 3. Token delta — what 8.2 still owes

Everything else in §1 is done. This is the whole remaining change to `shared/theme.py`
(**authored in `packing-tool`**, pulled here via `scripts/sync_shared.py` — never the
reverse):

1. Add `surface_sunken` (light `#E8E8EB`, dark `#08080B`).
2. Change dark `surface` `#0A0A0A` → `#101014`.
3. Add `accent_fill_hover` `#0A78C4` and `accent_fill_active` `#005A9E`, theme-independent.
4. Re-point `button_hover_light` / `button_hover_dark` at them.
5. Extend `_COLOR_FIELDS` with the three new tokens.
6. Extend `validate_theme`: assert `on_accent` ≥ 4.5:1 against **all three** fills, and
   assert every foreground clears its floor on **all four** planes — not just `surface`.
7. Delete the `ponytail:` comment at `shared/theme.py:309`; it is resolved by (6).
8. Widen light's six binding foregrounds so they clear their floors on the new
   `surface_sunken` plane (§2/C1, amended): `text_placeholder` `#686868`, `border`
   `#858585`, `status_info` `#006BB5`, `status_success` `#337635`, `status_warning`
   `#985A00`, `status_danger` `#CF180A` — with `accent_green` / `accent_orange` /
   `accent_red` carried along in lockstep by the alias-drift check.

Six tokens' worth of edit, plus (8)'s six one-to-two-unit foreground nudges. The acceptance test is the table in §2/C1 plus the three ratios
in §2/C4, as a fixture.

---

## 4. Status semantics — one vocabulary, both apps

Both sources land on the same rule, stated best by Parcker:

> **Colour carries urgency, tint carries authorship.** A plain dot means a person put the
> session in this state. A tinted chip means the system detected it — a lock went cold, a
> worker never came back.

Status is an **edge, a chip, or a tint — never a filled row** (Depot). Selection is a 2 px
`selection_border` ring on `selection_bg`, not an accent fill, so a row can show *selected*
and *blocked* at the same time.

Packing Tool session states (`sessions_list_widget.py` `STATUS_CONFIG`) today invent seven
hex values that no theme knows and no test measures — including `#27AE60` Active against
`#2ECC71` Completed, and `#E74C3C` Incomplete against `#C0392B` Abandoned: two pairs a
supervisor scanning a 200-row table has to read the label to separate.

| key | label | role | tint |
|---|---|---|---|
| `not_started` | Not Started | `text_secondary` | — |
| `in_progress` | Active | `status_info` | — |
| `paused` | Paused | `status_warning` | — |
| `stale` | Stale | `status_warning` | `_bg` |
| `completed` | Completed | `status_success` | — |
| `incomplete` | Incomplete | `status_danger` | — |
| `abandoned` | Abandoned | `status_danger` | `_bg` |

Shopify fulfillment states map onto the same four roles by the same authorship rule —
Ready → `status_success`, Blocked → `status_danger`, Repeat → `status_warning` + tint
(system-detected), Manual → `status_info`, No SKU → `status_info`, Review →
`status_warning`.

**The mapping table is the contract, not each app's private dictionary.** A state with no
equivalent gets a key here first.

`StatusDot` (already in `shared/theme.py`) **takes a role name and the active theme, not a
hex string.** Constructing it with a colour is what let the palette escape the theme in the
first place. Its 10 px default diameter stays — it reads at a 24 px row and at arm's length.

---

## 5. Component inventory — six, each earned by a screen

Ponytail rule: a component exists when two screens need it or one defect demands it.
Everything else stays a plain widget until a second call site appears.

| component | earned by | replaces |
|---|---|---|
| **NavRail** (56 px, `surface_sunken`, icon + label, no border) | every Depot screen | the tab bar; Parcker §09 app chrome |
| **CommandBar** (client selector, session id, status, primary action) | every Depot screen | client sidebar of 70 px cards → a dropdown; frees the page |
| **StatusChip** (role + optional tint, edge/chip variants) | 1a, 1b, 1c, 1e, Packer Mode | `STATUS_CONFIG`'s 7 hexes; Session Browser's raw combobox with hardcoded `blue`/`darkgreen`/`red` |
| **StatCard / KpiStrip** (`display_xl` numeral + `caption` sublabel) | 1a KPI strip, 1c lanes, Metrics tab | ad-hoc stat layouts |
| **ContextualSelectionBar** (appears only on selection: *"3 orders · 11 items selected"* + actions) | 1a, 1b | the 11-button row that reads as eleven equally urgent choices |
| **FilterBar** (search field + removable filter chips + count) | 1a, 1b, 1e | scattered filter controls |

`StatusDot` already exists — reuse, do not rebuild. `EmptyState` and `InlineMessage`
(*"Waiting for the PDF"*, *"Metrics not available"*) stay plain labels until a second call
site justifies them.

**Button hierarchy** (Parcker §06, Depot "Controls"): four variants selected with a Qt
property — `setProperty("variant", "primary"|"secondary"|"ghost"|"danger")` — matched in
QSS with an attribute selector. **One primary per screen.** The current global rule fills
every `QPushButton` with the accent, which is why Cancel, Close, Export CSV and Start
Packing all shout equally loud. Secondary is the default; ghost carries everything
reversible; danger is an *outline*, not a fill. No screen restyles a state inline — hover,
pressed, disabled, focus and selected are defined once per widget class.

---

## 6. Screens

### Ungated — valid whichever direction wins

Depot states this explicitly: the shell is common to 1a/1b/1c, so these can ship before the
direction decision.

- **1d Session Setup.** Four stacked group boxes → one linear three-step card: session →
  the two input files → run. Client selection leaves the page entirely and lives in the
  command bar. Allocation strategy (multi-item first / FIFO) becomes an explained choice,
  not a bare radio. A "Recent" strip lists the last five sessions.
- **1e Session Browser.** Eight columns of mixed widgets → one row per session: status as a
  chip, packing as a progress bar, comment as text you click to edit. **The whole row is
  the hit target.** Carries the known presentation debt: the raw status combobox, the
  per-row `QLineEdit` comment column (0 of 42 real sessions use it — remove or rethink,
  do not restyle), and the `ColumnConfigPanel` list collapse (~70 px, scroll-area
  starvation, same failure mode as the 2026-08-23 session-setup fix).
- **1f Tools.** The nested tab-inside-tab goes away: Reference Labels and Barcode Labels sit
  side by side, each a card reading top to bottom — inputs, options folded away, one
  action. ZPL and printer settings unfold only when Raw ZPL is picked.

### Gated on a user decision — Analysis Results

Depot's fault #3: *"the results table is one row per SKU line, but staff decide per
**order**. 1 842 rows to make 312 decisions."* Two of the three directions fix the unit, not
the styling — so this is a product decision, not a styling one, and it is **the user's to
make**.

| | direction | change | risk |
|---|---|---|---|
| **1a** | **Ledger** | same table, disciplined: 9 columns not 23, status as a left edge, KPIs above, the 11-button row replaced by search + contextual bar | lowest — everything maps 1:1 to an existing widget |
| **1b** | **Order & detail** | one row per *order* (312, not 1 842), blocker on the row, SKU lines and tag/note actions in a right-hand detail pane | medium — new pane, new selection model |
| **1c** | **Triage** | opens on the decision: three lanes (ship / blocked / review) plus a stock-pressure strip naming the SKUs blocking the most orders, so *"restock 4402 and 22 orders unlock"* reads in one glance. Table one click away | highest — new IA, but the biggest payoff |

This is the one blocking question in Phase 8. It gates item 8.8 only; 8.2 through 8.7 run
without it.

**Navigation guardrails, carried forward from the deleted 2026-08-25 scope doc because the
reasoning still holds** (the user accepted navigation-change risk deliberately; warehouse
staff use both apps daily, so nav changes mean retraining):

1. Navigation rework lands in **separate commits** from cosmetic restyle, so nav can be
   reverted independently if it does not survive contact with users.
2. **Structure and labels do not change in the same release.** The rail ships with the old
   labels verbatim; renames land a release later.

---

## 7. Acceptance tests

The spec is only real where a test asserts it.

1. **Contrast, all planes.** Every foreground token clears its stated floor against
   `surface_sunken`, `surface`, `surface_raised` and `surface_overlay` — in both themes.
   The tables in §2/C1 are the fixture.
2. **`on_accent` against all three fills** — `accent_fill`, `accent_fill_hover`,
   `accent_fill_active`, ≥ 4.5:1. This is the C4 class fix.
3. **No literals.** A lint rule fails the build on a hex string or CSS colour keyword in
   `gui/` (shopify) or `src/`→`gui/` (packing). 125 known hits today: shopify 61, packing
   64. Record the exact regex used as the completion measure rather than chasing 125.
4. **No appearance-token reads at new call sites.** The ten frozen aliases may be read by
   existing code only; a new read fails the lint.
5. **Points, not pixels.** No `font-size:` in px anywhere in widget code.
6. **Status roles resolve.** Every key in the §4 table maps to a token that exists in both
   themes; `StatusDot` rejects a hex argument.
7. **Legacy fields still exist.** ~180 call sites read them; their removal must fail here,
   not at paint time. (Already asserted by `tests/test_theme_contrast.py`.)
