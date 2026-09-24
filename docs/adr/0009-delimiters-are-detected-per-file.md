# 0009 — Delimiters are detected per file; a stored delimiter is an override

**Status:** Accepted, 2026-09-24
**Context:** `docs/superpowers/specs/2026-09-24-phase12-bundle3-order-data-integrity-design.md` §4

## Context

Each client profile stored one delimiter for orders files and one for stock
files. The loader was split on whether to trust them. Slot load and folder
validation ran `detect_csv_delimiter` and toasted "Loaded with ';' — settings
say ','". The analysis run, the folder merge and a stock re-read ignored
detection and used the stored value. So a file could pass validation and then be
parsed as a single column by the run. Almost every stored value was also a
default nobody had picked: `,` for orders, `;` for stock.

The owner asked for the delimiter to set itself, with a manual value reserved
for critical cases.

## Decision

**The setting is either `auto` or an override.** Under `auto`, every read of a
user-supplied CSV resolves the delimiter from that file through one function,
`csv_utils.resolve_delimiter`. A fixed character is honoured unconditionally.
Settings offers Auto plus the four common characters.

**Every existing profile was migrated to `auto`, once.** A marker
(`settings.delimiter_auto_migrated`) stops the migration from ever running
again, so an override set afterwards is permanent.

## Consequences

- The migration overwrites stored values and cannot tell a chosen `;` from a
  default one. A client whose files detection misreads needs its override set
  again, once. Accepted: the alternative kept Auto away from every existing
  client, which defeats the request.
- A folder may mix comma and semicolon files; each is read with its own
  delimiter.
- The merged file the app writes for a folder is comma-separated under Auto,
  and uses the override when there is one. It is never read with a character
  it was not written with.
- The "Save as default" toast is gone: there is no default left to save.
