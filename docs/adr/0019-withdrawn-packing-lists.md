# 0019: Packing lists an edit makes out of date are withdrawn

**Status:** Accepted, 2026-10-15
**Context:** `docs/superpowers/specs/2026-10-15-coverage-replay-snapshot-fixes-design.md`, finding 2.2 of the
2026-10-11 production snapshot (`docs/audit/10-coverage-and-snapshot.md`, AUDIT-10-4).

## Context

An operator wrote a packing list, then removed a line from an order (ALMA, 2026-10-02). The edit saved the
session state and left `packing_lists/ALL.json` as it was. The Packer opened the old list, packed the removed
line and never wrote it off. Nothing connected an edit to the lists already written, and the Packer cannot be
changed in this task.

## Decision

Each packing list records its **packing fingerprint**, a hash of the fulfillable orders' SKUs and quantities,
in `session_info.statistics.packing_list_fingerprints` when it is written. After an edit or an analysis re-run
the window compares the frame's fingerprint with each list's. A list that differs is out of date:

- an unstarted list (no `packing/<name>/` folder) moves to `packing_lists/withdrawn/`, XLSX and JSON together,
  on the session write queue. The Packer scans `packing_lists/*.json` non-recursively and never reads
  `withdrawn/`, so it can no longer open it;
- a started list stays where it is and is named in a toast, so the operator checks it with the packer;
- a regeneration that fails after the old list was written withdraws the old list as well.

Regenerating writes a fresh list and records its fingerprint. Tags and notes are not in the fingerprint, so a
tag edit never withdraws anything. A session written before this change records no fingerprints and is left
alone.

## Consequences

- After an edit that changes what is packed, the operator has to generate the lists again. The toast says so.
- A list the Packer already started still holds the old contents. The Packer-side fix (refusing a list older
  than the session's last edit) is future packing-tool work.
- A file another PC or the Packer holds open cannot be moved; it is logged and the list is not reported as
  withdrawn.
- The word is **withdrawn**, not stale: Stale is a PC's old copy of the session state (CONTEXT.md).
