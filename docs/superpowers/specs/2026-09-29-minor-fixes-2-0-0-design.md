# Minor fixes 2.0.0: raw-ZPL "Invert colors", Python 3.14 deprecations — design

Task: Todoist "minor fixes 2.0.0" (dev-runner run 14). Path: **bounded**. Two independent changes to existing
flows, no new subsystem. The owner answered the design questions on 2026-09-29, choosing the recommended option each
time. No mockup: the one UI change is a checkbox that copies the existing "Rotate 90°" row.

## 1. Barcode labels print white-on-black over raw ZPL

### What the owner reported

In raw-ZPL mode, **Barcode Generator** labels print with a black background. It started after the dependency update.
Reference Labels, which use the same raw-ZPL encoder, are not reported. barcode_tool works on the same printer.

### What the code does (checked 2026-09-29, dev VM, Python 3.14.4)

- `shopify_tool/label_printing.py` is a line-for-line port of barcode_tool's `zpl_print_service.py` and
  `template_renderer.py`. The pipeline is the same: pdfium greyscale render → `convert("1", dither=NONE)` →
  `ZebrafyImage(invert=True)` → `^XA ^PW ^LL ^GFA ^XZ`.
- Polarity is correct on this machine. A real Code-128 label and a real QR label from
  `barcode_processor.generate_*_labels_pdf` are 15.9% and 10.3% black in the raster, and the same share of
  `^GFA` bits are set (a set bit prints a dot). This holds with and without rotate and with `target_size_mm`.
- The bump did not change this: zebrafy 1.2.0 → 1.2.2 only adds `string_line_break`, and Pillow 11.3 and 12.3
  produce identical `^GFA` data.
- The existing tests never check polarity. `tests/test_label_printing.py` checks only `^XA`/`^XZ`/`^PW`/`^LL`.

So the inversion cannot be reproduced from source on Linux. It happens on the owner's Windows build, or in the
printer's state. The root cause is **not confirmed**. The fix below works whatever it turns out to be, and it adds
a log line that will tell us next time.

### Decision (owner-approved)

1. **"Invert colors" checkbox** in Print options, on its own row directly below "Rotate 90°". It is visible only
   in Raw ZPL mode, like the other ZPL rows. It is saved per scope (`reference_labels` / `barcode_generator`) under
   the new QSettings key `raw_zpl_invert` (bool, default `False`). The default keeps today's output for everyone.
   An operator whose labels come out white-on-black ticks it once, on that screen only.
   - Tooltip: `Tick if labels print white on black.`
   - Folded summary: after the rotate suffix, append `, colors inverted`. Example:
     `Prints raw ZPL to ZPL-RAW at 68 × 38 mm, rotated 90°, colors inverted`.
   - Spelling is "colors": the app's UI already uses US spelling ("Choose Color").
2. **`^LRN` in every job**, right after `^XA`. It forces the printer's label-reverse mode off. `^LR` persists
   between jobs and can be saved to the printer's memory, so a stuck `^LRY` from another program would invert
   everything. `^LRN` makes each job's polarity depend only on its own data. The checkbox then has one fixed
   meaning.
3. **One diagnostic log line per job** in `print_pdf_raw_zpl`, at INFO:
   `Raw ZPL: <n> label(s) to <target>, first label <p>% black`. A normal label is about 10–20% black, and an
   inverted raster is about 80–90%. The next report then tells us whether the raster (Windows render) or the
   printer inverts, without a debugging session.

### Seams and signatures

- `label_printing.image_to_zpl(image, rotate=False, invert=False) -> str`. `invert=True` flips the output
  polarity. It passes `invert=not invert` to `ZebrafyImage`, so the existing default stays `invert=True` inside
  zebrafy. Output is `^XA\n^LRN\n^PW{w}\n^LL{h}\n{field}\n^XZ\n`.
- `label_printing.print_pdf_raw_zpl(pdf_path, target, rotate=False, target_size_mm=None, invert=False)` passes
  `invert` to `image_to_zpl` and logs the line from item 3. The module gets `logger = logging.getLogger(__name__)`.
- `gui/pdf_printing.py`: `load_print_settings` / `save_print_settings` gain `raw_zpl_invert`.
  `_print_pdf_raw_zpl_mode` passes `invert=settings.get("raw_zpl_invert", False)`.
- `gui/components/print_options.py`: adds `self.raw_zpl_invert_check`, `current_settings()["raw_zpl_invert"]`,
  the visibility rule in `_update_zpl_controls_visible`, a `toggled → _on_edited` connection, and the summary suffix
  in `print_summary`.
- Driver mode is untouched.

### Rejected

- **Flip the hard-coded polarity for everyone.** That would break Reference Labels, which print correctly with the
  same encoder.
- **Auto-invert when a raster is mostly black.** Silent guessing. A label that is dark by design would flip.

## 2. Python 3.14 and the dependency bump (#349, #350)

### Findings (dev VM: Python 3.14.4, PySide6 6.11.2, pandas 3.0.5, numpy 2.5.3, Pillow 12.3.0)

- **Stable.** The full suite passes (2118 tests), `ruff check . --exclude shared` is clean, and the CI smoke test
  (`CI=1 run_dev.py`, offscreen) runs with `-W default` and prints no warnings from app code. CI and the release
  build already run on 3.14 (#350).
- The suite prints 54 warnings from **3 sources**:

  | Source | Warning | Fix |
  |---|---|---|
  | `gui/log_filter.py:26,30` | `QSortFilterProxyModel.invalidateFilter()` deprecated (Qt 6.10+) | Wrap each state change in `beginFilterChange()` … `endFilterChange()`. Both exist in PySide6 6.11.2, the new floor. |
  | `shopify_tool/rules.py:633` (45×, `tests/audit/test_03_rule_engine.py`) | pandas `UserWarning` "pattern … has match groups" from `str.contains(regex=True)` | Suppress that one message around the call. Groups are normal in operator-written rules such as `(DHL\|UPS)`, and `contains` ignores them. |
  | `tests/test_session_browser_1e.py:132` | deprecated `QMouseEvent` constructor without a global position | Use the overload that takes `localPos, globalPos` (both `QPointF`). |

- The local `.venv` is behind the new floors (pandas 3.0.5 < 3.0.6, pypdf 6.17 < 6.19, ruff 0.16.6 < 0.16.9,
  pyinstaller 6.22.2 < 6.22.3). CI installs fresh, so this only affects the dev VM. Refresh it with
  `.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt`. That is an operator step, not
  part of the PR.
- Nothing else in the new versions needs adopting. pandas 3 copy-on-write makes the old "avoid
  SettingWithCopyWarning" `.copy()` calls unnecessary. Removing them is churn with regression risk and no user
  benefit (owner chose not to). Python 3.14 deferred annotations make `from __future__ import annotations`
  redundant, but it is harmless.

### Decision (owner-approved)

Fix the 3 warning sources above, and nothing else. Success: the full suite runs with **0 warnings** from
`gui/`, `shopify_tool/` and `tests/`.

### Out of scope

- packing-tool stays on Python 3.11 CI (owner: Fulfilment Tool only). It has no ZPL code.
- No ADR. Every change here is small and easy to reverse.

## Testing

- `tests/test_label_printing.py`:
  - **polarity**: a mode-"1" image with a black left half encodes with the left half's bits set;
  - `invert=True` sets the right half's bits instead;
  - `^LRN` comes right after `^XA`;
  - `print_pdf_raw_zpl` forwards `invert`;
  - the log line reports a black percentage.
- `tests/test_pdf_printing.py`: the defaults/round-trip dicts include `raw_zpl_invert`, raw mode forwards `invert=`,
  and the three existing `assert_called_once_with` calls gain `invert=False`.
- `tests/test_print_options.py` and `tests/test_print_summary.py`: the checkbox shows only in ZPL mode, a toggle
  saves under the scope, it loads from saved settings, and the summary gets the suffix. The fixture defaults in
  `tests/conftest.py` gain `raw_zpl_invert: False`. The `_settings` defaults in `tests/test_print_summary.py` gain it
  too.
- Deprecations: the existing `test_log_filter.py` and `test_03_rule_engine.py` tests must still pass. The gate
  prints no warnings from those three sites.
- Gate: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check . --exclude shared`.
- Visual check: render `PrintOptions` in ZPL mode, open, to a PNG (offscreen, `widget.render(QImage)`) in both
  themes. Confirm the new row lines up under "Rotate 90°".
- Hardware check (owner, Windows): tick Invert colors on Barcode labels, print one label, and read the log line.
