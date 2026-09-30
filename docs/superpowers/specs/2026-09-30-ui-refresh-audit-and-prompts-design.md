# UI refresh: interface audit, Claude Design prompts, two bug fixes

**Task:** dev-runner run 27, Todoist 6hfpmXvXP4X7HJ9v: "can we think about improved UI and optimisation?
I'm interested in widening web integration to app, and better layouts. First do a check of the
interface, then create prompts for Claude Design for mockups. Looking for something like the new
Shopify style."
**Path:** architectural (it reopens ADR 0001 and sets the direction for every screen).
**Mockup followed:** none yet. This task produces the prompts the mockups will come from.

## Owner's decisions (2026-09-30)

| Question | Answer |
|---|---|
| What "widening web integration" means | More screens on the web tier (not a Shopify API connection) |
| What this task delivers | Audit + Claude Design prompts + the two bugs the audit found |
| Shopify look | Asked for "Polaris 2.0". No such library exists (see ADR 0016). **The Polaris look, rebuilt in our own CSS/QSS** |
| Depth | `box-shadow` allowed on the web tier; Qt stays flat |
| Prompt coverage | Shell + the five destinations + Client settings |
| Apps | Fulfilment Tool only. Packing Tool follows later |

## Deliverables

### Written at Stage A (done, on this branch)

1. `docs/design/ui-refresh/audit.md`: findings per screen, graded Bug / Major / Minor, with renders
   in `docs/design/ui-refresh/current/` (1366×768, light and dark, offscreen).
2. `docs/design/ui-refresh/prompts.md`: a style brief (§0) and seven screen prompts (§1 Shell, §2
   Setup, §3 Results, §4 Browse, §5 Logs, §6 Tools, §7 Client settings), with instructions for running
   them in one Claude Design project. The owner runs them; the outcome is approved HTML mockups
   under `docs/design/ui-refresh/mockups/`.
3. `docs/adr/0016-the-web-tier-grows-screen-by-screen.md`, with a pointer added to ADR 0001.

### Built at Stage B (the plan)

Two bugs from the audit. Nothing else changes in code.

#### Bug S1: a `StatePanel` whose text wraps is clipped

**Where:** `shared/components/state_panel.py`, owned by **packing-tool**. It is fixed there and
synced here with `scripts/sync_shared.py`. It shows in this app on Setup's "Choose a client to
begin".

**Cause (reproduced):** `outer.addWidget(self.card, 0, Qt.AlignCenter)`. A layout item with an
alignment is sized from `sizeHint()`, so the card's height never goes through the wrapped labels'
`heightForWidth()`. At the card's 360px minimum width, the cause label needs 36px and gets 22px.

**Fix:** centre horizontally with stretches instead of an alignment flag. Put the card in a
`QHBoxLayout` between two `addStretch(1)` and add that row to the outer `QVBoxLayout` between its
two existing stretches. Tested in a prototype: the label gets exactly its `heightForWidth()` (36 of
36), and the card grows from 92px to 110px. Rejected: `card.setMinimumHeight(card.heightForWidth(...))`.
It also works, but it is computed once and goes stale when a theme or density change moves the fonts.

**Test seam:** `StatePanel` alone. Build `nothing_loaded` with a cause long enough to wrap, `resize`
the panel to 1300×700, `show()`, process events, and assert that every `QLabel` in `panel.card` has
`height() >= heightForWidth(width())`. Goes in packing-tool's `tests/test_state_panel.py`.

#### Bug B1: Browse says "CLIENT_None has no sessions"

**Where:** `gui/session_browser_widget.py`, `_empty_reason` and `_update_empty_state`.

**Behaviour:** when the tree is empty, there are no sessions, and `current_client_id` is falsy,
`_empty_reason()` returns a new reason, `"no_client"`. `_update_empty_state` shows
`StatePanel.nothing_loaded("Choose a client", "Pick a client in the bar above to see its sessions.", "")`,
which has no button (`empty_panel.button is None`), because a new session needs a client. The
`"nothing"` panel stays as it is for a real client, and its text keeps the `CLIENT_` prefix, which is
how the file server names client folders.

The check goes only where `"nothing"` is decided (`"filtered" if self.sessions_data else …`), so the
`"filtered"` and `None` reasons are untouched.

**Test seam:** the existing `browser` fixture in `tests/test_session_browser_columns.py`
(`TestEmptyStates`). Set `current_client_id = None`, `sessions_data = []`, call `_populate_tree()`,
and assert the reason is `"no_client"`, `empty_panel.button is None`, and no label text in the panel
contains `"None"`.

## Out of scope

- Any restyle, and moving any screen to the web tier. Each screen gets its own task once its mockup
  is approved (ADR 0016).
- The `style_lint.py` shadow permission and a `card_shadow` token. These ship with the first PR that
  uses a shadow (ADR 0016).
- A Shopify Admin API connection.
- Packing Tool screens.

## Delivery

- **packing-tool** PR from branch `dr/11-can-we-think-about-improved-ui-and-optim`: the S1 fix and its
  test.
- **shopify-fulfillment-tool** PR from the same branch name: the docs above, the synced
  `shared/components/state_panel.py`, and the B1 fix and its test. It states that it depends on the
  packing-tool PR for `shared/`.
- Gates: this repo `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and
  `ruff check . --exclude shared`; packing-tool `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`.

## After this task

The owner runs `prompts.md` in Claude Design. Each approved mockup opens a new task: "Move <screen>
to the web tier per `docs/design/ui-refresh/mockups/<screen>.html`". Suggested order, from the audit's
severity: Shell tokens (canvas, card, shadow) first, then Setup, Browse, Tools, Client settings and
Logs.
