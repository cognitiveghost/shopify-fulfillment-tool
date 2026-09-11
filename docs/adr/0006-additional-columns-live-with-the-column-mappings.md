# ADR 0006 — Additional columns live with the column mappings

- **Status:** accepted, 2026-09-11 (Phase 9 Bundle 13)
- **Deciders:** repo owner, via the Bundle 13 spec
- **Scope:** the additional-columns list, and where the analysis reads it

## Decision

The additional-columns list is stored in the shopify config, at
`column_mappings.additional_columns`. Settings › Mappings writes it with the
Save that writes everything else.

`core.effective_additional_columns` reads that key whenever it is present, even
when it holds an empty list. When the key is absent, it falls back to
`client_config.ui_settings.table_view.additional_columns`.

## Context

The list's only editor was `ColumnConfigPanel`, and it wrote the client config
through `TableConfigManager.save_config`. Bundle 10 made Settings the one write,
and that write goes to the shopify config only. Bundle 10 also deleted the
panel's Settings page. Bundle 12 then removed its last entry point, so nothing
could edit the list, while `core.py` kept reading it on every run.

Bundle 13 moves the editor to Settings › Mappings. At run time `core.py` already
copies the list into `column_mappings["additional_columns"]`, and that is the
shape `analysis.run_analysis` consumes.

## Consequences

- **No migration.** A profile that has never been saved keeps working through
  the fallback.
- **Stale old key.** After a profile's first Settings save, the client-config
  key is stale: nothing writes it any more. It is left in place, not deleted.
- **One reader.** Read the list only through `effective_additional_columns`.
  Code that reads either location directly sees the wrong list for half the
  profiles on the share.

## Alternatives considered

**Settings also writes the client config.** This keeps the key where it was.
Rejected: it means two files and two locks, a Save that can half-succeed, and
the end of Bundle 10's rule that Settings saves once.

**Migrate on load.** This would move the key into the shopify config the first
time a profile loads. Rejected: it writes every profile on the share just by
opening it, and the owner declined profile migrations in Bundle 12.
