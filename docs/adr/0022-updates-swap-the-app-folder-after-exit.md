# 0022: An update swaps the app folder after the app exits

**Status:** Accepted, 2026-10-15
**Context:** `docs/superpowers/specs/2026-10-15-app-shell-i18n-updater-icon-design.md` (section 4). Owner
decisions, runner questions 80 and 81.

## Context

Both tools ship as a zipped PyInstaller folder on a public GitHub release, and are installed by unzipping. Some
PCs may run a copy on the server share that other PCs also have open. Windows will not replace a running exe.
It will not rename a folder while any process, on any PC, has a file in it open. The owner wants the operator
to choose when to update, never mid-task.

## Decision

`shared/updater.py` asks GitHub for the latest release at startup and offers it. On the operator's go, it
downloads the zip, checks its SHA-256 and unpacks it beside the app folder. At quit, a detached `.cmd` waits for
the app's process to exit, renames the app folder to `<name>.previous` (retrying for 60 s), moves the new
folder in, copies across the files the release does not ship (`config.ini`), and starts the new exe. If the
rename never succeeds, it restarts the old copy and leaves a marker that the next start reports.

## Consequences

- One mechanism covers a per-PC folder and a shared server copy: the folder rename is the lock that tells
  whether anyone still has the copy open.
- `<name>.previous` is a one-step manual rollback.
- The trust root is the GitHub repo and HTTPS: the `.sha256` asset sits beside the zip and proves only that
  the download is intact. A compromised repo could ship a bad update. Code signing would be the upgrade.
- The swap runs as a `.cmd` with no test on Linux, only a text test. It is on the Windows checklist of every PR
  that changes it.
- A folder the user cannot write to cannot update itself, and the app sends the operator to the release page
  instead.
