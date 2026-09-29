# CI on Python 3.14 so Dependabot #349 installs; #348 checked — design

Task: Todoist "Bump the python group goes with error" (dev-runner run 11). Path: **bounded** (CI config only,
no app code). Design approved by the owner 2026-09-29.

## Problem

Two open Dependabot PRs on `cognitiveghost/shopify-fulfillment-tool`:

- **#349** "Bump the python group with 25 updates" (branch `dependabot/pip/python-285ee382d1`) raises the `>=`
  floors in `requirements.txt` and `requirements-dev.txt`. Every "Run Tests" job fails in *Install dependencies*:
  `ERROR: No matching distribution found for numpy>=2.5.3`. numpy 2.5 requires Python >= 3.12. CI and the
  Windows release build pin `python-version: '3.11'` in `.github/workflows/build_release.yml`. No test ever runs.
- **#348** "Bump the actions group with 5 updates" is green, but its checks cover only the Ubuntu jobs.

Facts that shape the fix:

- `main`'s CI on 3.11 already resolves pandas 3.0.6, pytest 9.1.1, ruff 0.16.9, PySide6 6.11.2, reportlab 5.0.1,
  pyinstaller 6.22.3, and passes. So numpy 2.5.3 is the only #349 bump that CI has not already exercised.
- The dev VM runs Python 3.14.4 (`/usr/bin/python3.14`) with numpy 2.5.3 and pandas 3.0.5.
- Every compiled dependency publishes a `win_amd64` wheel usable on 3.14, checked on PyPI 2026-09-29: numpy,
  pandas, pikepdf, pillow, pywin32, lxml, cffi, brotli, zopfli, fonttools, PySide6-Essentials/shiboken6
  (abi3), pypdfium2 and pyinstaller. reportlab is pure-Python.
- Under SPEC 0, numpy drops each Python version about 3 years after its release. 3.12 support is ending about
  now, so 3.14 gives the longest runway.

## Decision (owner-approved)

1. **CI and the release build move from Python 3.11 to 3.14.** Change all three `python-version: '3.11'` lines in
   `.github/workflows/build_release.yml` (jobs `verify`, `version`, `build`) to `'3.14'`. This changes the Python
   bundled into the shipped Windows exe, so the fix PR carries the `windows-build` label and its "Build
   Executable" job must pass. That job freezes with PyInstaller and verifies the bundled assets.
2. `README.md` line "Python 3.14 on the dev machine; CI and release builds use 3.11." becomes
   "Python 3.14 on the dev machine, in CI and in release builds."
3. **No requirements edits in the fix PR.** #349 stays Dependabot's. Once the fix is on `main`, the owner comments
   `@dependabot rebase` on #349 and its CI re-runs on 3.14.
4. **Before opening the fix PR**, #349's exact requirement files are installed into a throwaway Python 3.14 venv
   and the full CI gate (ruff, headless smoke test, pytest) runs green locally. If it does not, stop: fixing a
   package incompatibility is a new decision for the owner, not part of this change.
5. **#348 needs no code change.** Its release notes were reviewed against how the workflow uses each action:

   | Action | Bump | Breaking change | Affects us? |
   |---|---|---|---|
   | actions/checkout | v4→v7 | Node 24 (runner ≥ 2.327.1); credentials persisted to a separate file; v7 blocks fork-PR checkout under `pull_request_target`/`workflow_run` | No: GitHub-hosted runners; we use `pull_request`; `persist-credentials: false` still honoured |
   | actions/setup-python | v5→v7 | Node 24; `pip-install` input removed | No: input not used |
   | actions/upload-artifact | v4→v7 | Node 24; ESM; new optional `archive` input | No |
   | actions/download-artifact | v4→v8 | v5: path change for downloads **by ID**; v8: digest mismatch now errors | No: we download by `name`, same run; erroring on a bad digest is what we want |
   | actions/attest-build-provenance | v2→v4 | Now a wrapper over `actions/attest` | No: `subject-path` still supported; release job already has `id-token: write` + `attestations: write` |

   Verification: add the `windows-build` label to #348 so "Build Executable" runs `upload-artifact@v7`.
   `download-artifact@v8` and `attest-build-provenance@v4` run only in the `release` job, first at the owner's
   next real release. The owner accepted this over cutting a pre-release.
6. **Merge order (owner does all merges):** #348 and the fix PR in either order. Both edit neighbouring lines of
   `build_release.yml`. If the fix lands first, Dependabot rebases #348 itself. If #348 lands first, the fix branch
   is rebased onto `origin/main` before merge. Then `@dependabot rebase` on #349.

## Out of scope

- packing-tool: both its Dependabot PRs (#191, #192) are green, and pandas/numpy are unpinned there. It stays on
  3.11. `shared/` keeps being tested there on 3.11, the stricter of the two.
- `dependabot.yml` changes (ignore rules, versioning strategy). Not needed once CI is on 3.14.
- No ADR: a one-line, easily reversed CI setting.
