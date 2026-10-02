# 0016 — The web tier grows screen by screen, in a Polaris look we build ourselves

**Status:** Accepted, 2026-09-30
**Context:** `docs/superpowers/specs/2026-09-30-ui-refresh-audit-and-prompts-design.md`,
`docs/design/ui-refresh/audit.md`. Supersedes two parts of ADR 0001: the one-screen cap, and the
`box-shadow` ban for web assets. Everything else in ADR 0001 stands.

## Decision

1. **More screens may move to the web tier.** ADR 0001 capped the tier at Analysis Results and
   refused to spend a second slot. The owner has lifted the cap (2026-09-30). A screen moves only
   when it has an approved mockup (`docs/design/ui-refresh/mockups/`), in its own task, one screen
   per task. The shell (rail, command bar, status line) stays Qt.
2. **The look is the current Shopify admin (Polaris design language), rebuilt in our own CSS and QSS
   from `shared/theme.py` tokens.** Polaris is a reference, never a dependency.
3. **`box-shadow` is allowed in web assets.** The Qt tier stays flat. Gradients, transitions,
   transforms, opacity and px font sizes stay banned on both tiers.

## Why

- Two Qt rebuilds of Results did not fix it, and the web rebuild did (ADR 0001). The 2026-09-30 audit
  finds the other screens weak in the same way (no page structure, wasted canvas, cards with no rule)
  and the gap between Results and everything else is now the app's biggest visual problem.
- **Polaris cannot be imported.** Polaris React is deprecated (October 2025). Its successor, Polaris
  web components (1.x), is served only from `cdn.shopify.com` for apps embedded in Shopify admin with
  App Bridge. Its licence limits use to software that works with Shopify and restricts stand-alone
  apps. Its Shadow DOM refuses our tokens and dark theme, and loading it at runtime breaks the app
  whenever a warehouse PC loses internet.
- Polaris cards depend on a soft shadow for depth. ADR 0001 banned `box-shadow` so the two tiers would
  match, but once most screens are web, the only Qt surfaces left are the shell's, and those do not
  need depth.

## Consequences

- Every screen that moves adds a bridge surface like `ResultsBridge`. That tax is why ADR 0001 capped
  the tier, and it is still real: each move is priced in its own spec.
- `shared/style_lint.py` allows `box-shadow` in a web asset since phase 2 (2026-10-01), and only when its
  whole value is `var(--card-shadow)`, `var(--overlay-shadow)` or `none`. Any other shadow is still a
  finding, so a shadow is always one of the theme's two tokens. The lint is shared, so the allowance reaches
  Packing Tool at its next sync; its own ADR 0001 still bans shadows until a Packing Tool spec decides
  otherwise.
- A Qt child widget still cannot paint above a `QWebEngineView` (ADR 0007), so each web screen keeps
  drawing its own toasts.
- Setup moved in phase 3 (2026-10-01) with the second bridge, `SetupBridge`. What every bridge shares (the
  theme, the toast, the mount) is `gui/web_page.py`.
- Browse moved in phase 4 (2026-10-01) with the third bridge, `BrowseBridge`, and a third view, on the
  phase 3 measurement (about 31 MB a view). Its page owns its view state (tab, search, checked rows), as
  the results document does; Python owns every fact about a session.
- Tools moved in phase 5 (2026-10-02) with the fourth bridge, `ToolsBridge`, and a fourth view, on the same
  measurement. Its page owns only which menu and which Label setup fold is open; Python owns every fact
  about a tool.
- Logs moved in phase 6 (2026-10-02) with the fifth bridge, `LogsBridge`, and a fifth view, on the same
  measurement. No Qt page is left in the shell. Its page keeps the rows it is sent and owns its whole view
  state (source, level, search, wrap, follow, open rows); Python keeps the entries, words every row and
  streams rows in batches, never one message a line.
- Client settings began moving in phase 7 (2026-10-02) with the sixth bridge, `SettingsBridge`, and a sixth
  view, which lives only while the dialog is open. Three pages moved: General, Orders mapping and Stock
  mapping. The dialog's frame stays Qt until its last Qt page has moved, because a Qt page cannot be drawn
  over a web view (ADR 0007). Python owns every value and every sentence of a page, in a draft; the page
  owns which menu is open.

## What would reverse it

A frozen Windows build where a second `QWebEngineView` costs noticeably more memory or startup time
on the warehouse PCs, measured over RDP. Point 1 would then return to one web view hosting several
screens, or stop at the screens already moved.

Measured on Linux, offscreen, 2026-10-01 (phase 3 spec section 2): the first view costs about 195 MB,
each further view about 31 MB and at most 0.15 s. Two views total about 372 MB against 340 MB for one.
A frozen Windows build over RDP has not been measured; that check is in the phase 3 PR and is done on a
warehouse PC before the release that carries Setup.
