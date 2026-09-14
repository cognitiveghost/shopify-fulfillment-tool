# 0007 — The Results screen toasts inside the document

**Status:** accepted, 2026-09-14 (Phase 9 Bundle 14, item 9.17)
**Context:** ADR 0001 (Analysis Results renders in a `QWebEngineView`),
Bundle 9 § 4.1 (the toast route), Bundle 13 § 9 (which deferred this here)

## The decision

Every toast raised by the Results screen — the selection bar's bulk actions and
the detail pane's per-order verbs alike — is emitted into the web document
through `ResultsBridge.toastRaised` and drawn by `gui/web/bulk.js`. The Qt
`Toast` component is not used on this screen. Everywhere else in both apps, it
still is.

Two implementations, one appearance. `shared/style_lint.py` scans both tiers
and enforces the shared tokens; the duration, badge threshold, width and margin
are copied from `gui/components/toast.py` and named in Bundle 14's spec § 6 so
the copy is checkable.

## Why

`Toast` is a `QFrame` parented to its host window and positioned over the
window's bottom-right corner. The Results tab is entirely a `QWebEngineView`,
whose native compositing surface draws above sibling widgets. A Qt toast raised
from this screen has nowhere to land that is not behind the page.

The alternatives were worse:

- **Make the toast a top-level window.** It would then float over everything,
  survive the window losing focus, and need its own move-with-parent handling
  on a multi-monitor warehouse PC. A frameless always-on-top window for a
  four-second confirmation is the wrong object.
- **Leave the pane's toasts in Qt and only make the bulk ones web.** This was
  the smaller diff, and it is what Bundle 13 shipped by default when it
  deferred the question. It leaves three verbs — exclude an order, remove a
  line, toggle a status — confirming into a surface the operator cannot see.
- **Give up the web tier.** ADR 0001 settled that, and none of the arguments
  here reopen it.

## The cost, stated plainly

The toast now exists twice, and the two copies can drift. That is a real cost
and it is accepted knowingly: the appearance is linted, the constants are
written down beside each other, and the alternative was a confirmation nobody
can see.

It also means a Results toast disappears when the screen is left, where a Qt
toast would follow the window. For a message that is over in four seconds and
carries an Undo also reachable from the rail, that is not a loss.

## What would reverse it

Qt gaining a reliable way to composite a child widget above a
`QWebEngineView`'s surface on Windows, which is the only platform this app
ships to. If that happens, the web toast is deleted and the eleven call sites
in `actions_handler.py` go back to `toast()`.
