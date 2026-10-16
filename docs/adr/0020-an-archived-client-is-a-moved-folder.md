# 0020: An archived client is a moved folder

**Status:** Accepted, 2026-10-15
**Context:** `docs/superpowers/specs/2026-10-15-client-management-and-switch-freezes-design.md` (A1). Owner
decision, runner question 77.

## Context

Clients that no longer ship kept filling the client list in both tools, and nothing could remove one. Fulfilment
and Packing both list clients as the directories under `Clients/` whose name starts with `CLIENT_`, and each
reads its own config file (`client_config.json` / `packer_config.json`). A flag inside a config would be seen by
one tool only, and packing-tool would need its own change and release to honour it.

## Decision

Archiving a client renames `Clients/CLIENT_<ID>` to `Clients/_archive/CLIENT_<ID>` and `Sessions/CLIENT_<ID>` to
`Sessions/_archive/CLIENT_<ID>`. Restoring renames them back. `_archive` does not start with `CLIENT_`, so both
tools stop listing the client with no code change in either listing. Sessions, history and stats are kept.

Deleting is permanent and allowed only for a live client with no session folders: it exists to undo a mistaken
create. A client with history can only be archived. An archived ID cannot be reused by a new client, so a
restore never collides.

## Consequences

- A rename fails on Windows while another PC holds a file inside the folder open. The app reports it and
  undoes a half-done archive (client moved, sessions not).
- A PC that has the client open when it is archived finds out at its next list refresh. Nothing
  coordinates PCs; archive is rare and deliberate. A save it makes before then recreates
  `Sessions/CLIENT_X/<session>/` (writes create their parent folders), and restore then refuses until
  someone moves those folders into the archived one by hand.
- Anything that later reads `Clients/` or `Sessions/` by walking every child must skip `_archive`.
