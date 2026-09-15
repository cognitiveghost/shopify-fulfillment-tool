# 0008 — Config writes are atomic, not locked

**Status:** Accepted, 2026-09-15
**Context:** `docs/superpowers/specs/2026-09-15-post-phase9-quickfixes-design.md` §1, §7 Q3

## Context

Client config, shopify config and the groups file all live on a Windows file
server reached over UNC, and several warehouse PCs run the app at once. Since
before Phase 9, `profile_manager` and `groups_manager` each carried a
hand-rolled "safe save": write to `<name>.tmp`, take an `msvcrt.locking` byte
range on it, `shutil.move` it into place, and retry the whole thing five or ten
times with a sleep between attempts.

It did not work. A Windows build on 2026-09-14 logged
`FileNotFoundError` and `PermissionError [WinError 32]` on
`client_config.tmp`, `Failed to save client config after 5 attempts`, and —
the one that matters — `JSONDecodeError: Extra data: line 112 column 2` when
reading `CLIENT_ALMA`'s config back. The config on the share was corrupt.

Three defects, compounding:

1. The temp file had a **fixed name**, so concurrent writers fought over one
   path. One writer's `shutil.move` took the file another was still holding.
2. The lock was taken on the **temp file**, which no reader ever opens. The
   contended file, `client_config.json`, was never locked. The lock protected
   nothing.
3. `shutil.move` is **not atomic onto an existing destination**. Windows
   `os.rename` refuses an existing target, so `shutil.move` falls back to
   `copy2` + `unlink` — a byte copy into the live file. Write fewer bytes than
   the file already held and the old tail survives. That is the `Extra data`
   corruption, exactly.

## Decision

**Delete the locking machinery. Route every config write through
`shared/atomic_write.py`'s `atomic_write_json`, and accept last-writer-wins.**

`atomic_write_json` creates a uniquely-named temp file in the destination
directory via `tempfile.mkstemp`, writes it, and calls `Path.replace()` —
`os.replace`, which is atomic on Windows as well as POSIX. It already retries
for transient SMB errors and cleans up its temp file on failure.

We do **not** add revision stamps, a merge pass, or a conflict dialog.

## Consequences

The file is always valid JSON. A reader sees either the whole old document or
the whole new one, never a splice of both. The `.tmp` races cannot recur,
because no two writers share a temp path.

Roughly 150 lines go away: `_save_with_windows_lock` and `_save_with_unix_lock`
in both managers, their retry/timeout loops, and the `msvcrt`/`fcntl` imports.
The "attempt n/5" log spam goes with them, and saves stop blocking the UI for
up to five seconds.

**Two PCs editing the same client's settings at the same moment: the second
save wins and the first operator's change is lost silently.** This is accepted.
The harm being fixed was corruption, not clobbering; a clash needs two people
in the same client's Settings dialog within the same second, which is rare in a
warehouse where each operator works a different client. Buying protection would
cost an extra network read on every save (merge) or a failure dialog an
operator cannot act on (conflict detection) — both worse trades than the loss
they prevent.

If lost edits ever show up in practice, the upgrade is the merge variant:
re-read the file immediately before `replace()` and overlay only the section
that changed. That is a change inside one function and does not disturb callers.

## Alternatives considered

**Fix the lock in place** — unique temp name and `os.replace`, but keep
`msvcrt.locking`. Rejected: the lock is on the temp file, so it protects
nothing; correcting it would mean locking the destination, which is where SMB
byte-range locks are least reliable. It would also preserve the retry and
timeout machinery, all of which exists to work around the bug being removed.

**Move the fix into `shared/`** — rejected as unnecessary. `shared/` is owned
by `packing-tool` and synced one-way (see `CLAUDE.md`), and
`shared/atomic_write.py` is already correct. Only this repo's callers were
wrong, so no cross-repo sync is involved.
