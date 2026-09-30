# 0017 — Fulfilment Tool owns `shared/`; Packing Tool pulls a pinned copy

**Status:** Accepted, 2026-09-30
**Context:** `docs/superpowers/specs/2026-09-30-shared-canonical-swap-design.md`. Reverses the
direction set by packing-tool's shared-unification spec (2026-07-25). ADR 0016's aside that
`shared/style_lint.py` is "owned by packing-tool" is out of date from here on.

## Decision

1. `shopify-fulfillment-tool/shared/` is the canonical source. It is edited, linted and unit-tested
   here.
2. packing-tool mirrors it with its own `scripts/sync_shared.py`, which deletes and re-copies the
   folder and writes the source commit to `scripts/shared_synced_from.txt`.
3. packing-tool's CI checks its `shared/` against this repo **at that pinned commit**, not against
   `main`.

## Why

- The UI redesign (ADR 0016) is done here first and adopted by Packing Tool later. Authoring
  `shared/` in the repo that is not being redesigned meant every redesign change started in the
  wrong place.
- **Pinned, not `main`.** Packing Tool will lag on purpose while the redesign lands. A check against
  `main` would turn every packing-tool PR red whenever `shared/` moved here, until someone synced,
  and that would push people into syncing changes Packing Tool is not ready for. The pin still fails
  a hand edit, which is the one thing the check exists to catch.
- **Mirror, not copy.** The old script only copied files over, so a file renamed or deleted upstream
  would linger in the copy. The redesign renames things.
- A package or a git submodule would retire the copy altogether. Both need build and packaging
  changes in two PyInstaller apps for no gain the copy does not already give.

## Consequences

- A `shared/` change here reaches Packing Tool only when packing-tool syncs. That sync is where
  Packing Tool's breakage shows up, so a PR here that will need packing-tool work says so.
- The sync refuses a source whose `shared/` has uncommitted or untracked changes, because the
  recorded SHA would not match what was copied. The recorded commit must be pushed, or packing-tool's
  CI fails at checkout.
- `~/.claude/hooks/shared-guard.sh` on the dev VM now blocks edits to `packing-tool/shared/`.
