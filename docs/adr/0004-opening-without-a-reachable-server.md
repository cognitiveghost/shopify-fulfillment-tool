# ADR 0004 — The window opens even when the server is not reachable

Status: accepted · 2026-09-04 · supersedes nothing · consumed by Bundle 4
(9.7–9.9, the shell)

## Context

Before this bundle, `MainWindow._init_managers()` called
`ProfileManager()` — which raises `NetworkError` when the file server is
unreachable — inside a `while True` loop: on failure it offered a modal
path-recovery prompt (`prompt_for_recovery_path`), and on decline called
`QApplication.quit()`. There was no code path in which the window opened
with an unreachable share. "A launch with an unreachable share renders the
first-run screen" (9.9) was therefore not a layout task; it was a change to
the startup contract, and the largest piece of work in the bundle.

Three briefs (9.7, 9.8, 9.9) described the shell's chrome and its states.
None of them named this. The gap surfaced only when 9.9's screen was traced
back to the code path that would have to reach it, and none did.

## Options considered

**A — Keep the modal, degrade only on decline.** The window would open
degraded when a user actively dismissed the recovery prompt, but every user
who has not yet learned to dismiss it still hits `QApplication.quit()` on
first launch. This ships 9.9's screen for a fraction of the audience it is
meant to serve — the one who has not seen the prompt before — and keeps the
two-path startup (modal-then-maybe-quit, versus degrade) that the disabled
rail and Setup panel were built to replace with one.

**B — Defer 9.9.** Cutting the first-run screen from this bundle removes the
part it was named for — the roadmap's own accounting puts it at roughly 40%
of the bundle — and leaves the modal-or-quit contract in place for a launch
this bundle otherwise assumes is possible.

**C — Open degraded, always.** `ProfileManager` gains
`require_connection: bool = True`; passing `False` sets
`is_network_available = False` on an unreachable share and returns instead of
raising. `MainWindow` gains `connectionChanged = Signal(bool)`, emitted once
after `create_widgets()` and again whenever `ConnectionSettingsDialog`
returns a working path. The modal recovery prompt is not lost — it is what
"Server connection…" (in the command-bar overflow, and in the first-run
empty state) now opens.

Decided: **C**, by the repo owner, 2026-09-04.

## Why the disabling is the guard, not a null check

Every path `ProfileManager` publishes (`base_path`, `clients_dir`, …) is
still a real `Path` when degraded — `require_connection=False` never
substitutes `None`. `SessionManager`, `GroupsManager` and
`TableConfigManager` all take the manager, not the share, and none of their
methods runs against an unreachable path unless a caller is already
reachable through a control that `connectionChanged` did not disable.

The alternative — `ProfileManager(base_path=None)` on failure, with a
`None`-guard at each of the eleven call sites that read it — was rejected
before this bundle started. It scales badly (a twelfth call site is a twelfth
guard to remember) and it duplicates a check the disabled rail already makes
for free. `_on_connection_changed` is written on the premise that no call
site below it carries a `None`-check, because none of them is reachable while
`connected` is `False`: if a control that touches the share is ever left
enabled while disconnected, that is the bug this ADR's design is meant to
surface — not a missing guard three layers down.

## A bug this change exposed

`GroupsManager.__init__` did an unguarded
`self.clients_dir.mkdir(parents=True, exist_ok=True)` at construction. Before
this bundle, `_init_managers()` never reached it with an unreachable share —
`ProfileManager()` had already raised and the loop above never fell through.
With `require_connection=False`, construction proceeds, `GroupsManager`'s
`mkdir` raises `OSError`, and `_init_managers`'s existing
`except Exception: QMessageBox.critical(...); QApplication.quit()` catches
it — reintroducing the exact quit-on-launch behavior this ADR removes,
through a second path, and under the offscreen QPA test platform a
`QMessageBox.critical()` with no user to click it blocks forever rather than
returning. `GroupsManager.__init__` now catches `OSError` around the `mkdir`
and returns early, logging a warning; `load_groups()` already tolerates a
missing `groups_path`, so nothing downstream needed a second change.

## Consequences

- `ProfileManager()` (no keyword) still raises `NetworkError` on an
  unreachable share — every existing caller that does not pass
  `require_connection=False` keeps its original contract.
- `MainWindow.is_connected()` and `connectionChanged` become the one signal
  every degradable control is wired to: the rail (`Results`, `Browse`,
  `Tools` — items 1, 2, 4 — disabled, never hidden), the Setup stack (page 0,
  a `StatePanel`, versus page 1, the form), the command bar
  (`BarState.NO_CLIENT`), and the status-bar chip.
- A future manager constructed inside `_init_managers()` that touches disk
  eagerly will reproduce this bug unless its constructor is audited against
  a degraded `ProfileManager` the same way `GroupsManager`'s was here.
