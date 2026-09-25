# 0011 — A stale session state is refused, not locked or merged

**Status:** Accepted, 2026-09-25
**Context:** `docs/superpowers/specs/2026-09-25-phase14-bundle2-session-safety-design.md`

## Context

Every edit rewrites the whole session state (`analysis/current_state.pkl`) from
one PC's memory. When two PCs have the same session open, the second PC to save
silently undoes the first PC's edits (AUDIT-05-3). A held order goes back to
Fulfillable and ships. Packing Tool solves the same problem with a session lock
plus a heartbeat, and a second PC opens the session read-only.

## Decision

**This tool checks the state before writing it and does not lock the session.**
Each PC records a stamp of the state, `(mtime_ns, size)` of the pickle, when it
loads, saves or analyses. A save whose stamp no longer matches the file is
refused, and the operator is told to reopen the session. Generate reports and
Export selection run the same check, so a PC that never edits can't ship a
stale copy either. The check and the pickle replace run under a short sidecar
file lock (`current_state.pkl.lock`), held for milliseconds, never for the
whole session. `shopify_tool/session_state.py` owns all of this.

Rejected:
- **A session lock with a heartbeat** (Packing Tool's model). It needs stale-lock
  recovery, a read-only mode through every edit path, and takeover UX. That is
  far more code for a case the owner considers rare: two PCs working one
  client's session at the same time.
- **Merging the two frames.** Edits are whole-order rewrites plus derived stock
  (ADR 0010), so a row-level merge could produce a state that neither PC saw.

## Consequences

- The PC that saves first wins, and the other PC is told, instead of losing work
  without knowing. Its screen still shows the refused edit until it reopens.
- The undo history (`operations_history.json`) is still last-writer-wins. It
  can list an edit that the state doesn't contain.
- Any new code that writes `current_state.pkl` goes through
  `session_state.save_state`, and any new code that exports from the in-memory
  frame calls the stale check first. `core.run_full_analysis` writes the pickle
  directly, as a deliberate full replacement. The PC that ran the analysis
  re-stamps afterwards, and every other PC becomes stale.
- `(mtime_ns, size)` misses two same-size saves within one file-time tick.
  If that ever shows up, the upgrade is a version token written with the state.
