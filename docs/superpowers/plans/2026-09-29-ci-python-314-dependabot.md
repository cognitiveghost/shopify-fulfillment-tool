# CI Python 3.14 for Dependabot #349 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get Dependabot PRs #349 (python group) and #348 (actions group) mergeable by moving CI and the Windows
release build from Python 3.11 to 3.14.

**Architecture:** A 4-line change: three `python-version` lines in `.github/workflows/build_release.yml` and one
README line. Before it, a throwaway Python 3.14 venv built from #349's exact requirement files runs the full CI gate
locally. After it, a PR with the `windows-build` label proves the frozen Windows exe still builds on 3.14. #348 gets
the same label and a comment recording the release-notes review. No requirements edits: #349 stays Dependabot's.

**Tech Stack:** GitHub Actions, pip, PyInstaller (Windows job), pytest + ruff (gate).

**Spec:** `docs/superpowers/specs/2026-09-29-ci-python-314-dependabot-design.md`. Read it first. It holds the
failure evidence, the wheel survey and the #348 release-notes table this plan relies on.

## Global Constraints

- Target Python is exactly `'3.14'` (quoted string) in all three `python-version:` lines. Leave nothing on `'3.11'`.
- Do not edit `requirements.txt`, `requirements-dev.txt`, `.github/dependabot.yml`, or anything under `shared/`.
- Do not push to, or edit, the Dependabot branches of #348/#349. Do not merge any PR (the hook refuses `gh pr merge`).
- Git: `/usr/bin/git`, one plain git command per Bash call, no `$VAR` paths, no `&&`/`;` chaining, and no `rtk git`.
  Commit with `git commit -F <absolute path to message file>`.
- Branch is `dr/6-bump-the-python-group-goes-with-error`. Worktree is
  `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-6`. Its `.venv` is a symlink to the
  main checkout's venv: **never** delete or recreate it.
- pytest commands must contain `QT_QPA_PLATFORM=offscreen` or the pytest-guard hook blocks them.
- Temp files go in your job's tmp dir: the absolute path given as `$CLAUDE_JOB_DIR/tmp` in your system prompt. It is
  written below as `<JOBTMP>`; substitute the literal absolute path.
- `gh pr edit` fails on this repo (Projects classic). Use the `gh api` forms shown below.

## Review Focus

1. **A #349 package breaks on 3.14 or on numpy 2.5.3.** Task 1 runs the full gate on #349's exact files before any
   PR exists. On any failure, stop and report; do not patch.
2. **The frozen Windows exe fails to build or misses assets on 3.14** (PyInstaller hooks, QtWebEngineProcess, GTK
   DLLs). Task 3 requires the labelled "Build Executable" job to be green, including "Verify bundled assets shipped".
3. **A stray `'3.11'` left in the workflow**, which splits test and build interpreters. Task 2 greps for it.
4. **Merge conflict between #348 and the fix PR** (neighbouring lines). Task 3 explains the rebase path in the PR
   body. The implementer does not resolve it on Dependabot's branch.
5. **#349's CI re-runs on stale workflow.** It will not re-run until the fix is on `main` and #349 is rebased. The
   PR body tells the owner to comment `@dependabot rebase` after merging.

---

### Task 1: Prove #349's requirements pass the gate on Python 3.14 (no commit)

**Files:** none in the repo. Throwaway venv in `<JOBTMP>/venv349`, requirement files in `<JOBTMP>/pr349/`.

**Interfaces:**
- Consumes: #349 head branch `dependabot/pip/python-285ee382d1` on `cognitiveghost/shopify-fulfillment-tool`.
- Produces: a pass/fail verdict, recorded later in the Task 3 PR body.

- [ ] **Step 1: Fetch #349's two requirement files**

```bash
mkdir -p <JOBTMP>/pr349
```
```bash
gh api "repos/cognitiveghost/shopify-fulfillment-tool/contents/requirements.txt?ref=dependabot/pip/python-285ee382d1" -H "Accept: application/vnd.github.raw" > <JOBTMP>/pr349/requirements.txt
```
```bash
gh api "repos/cognitiveghost/shopify-fulfillment-tool/contents/requirements-dev.txt?ref=dependabot/pip/python-285ee382d1" -H "Accept: application/vnd.github.raw" > <JOBTMP>/pr349/requirements-dev.txt
```
Check: `grep -n 'numpy' <JOBTMP>/pr349/requirements.txt` prints `numpy>=2.5.3`. If the branch has moved
(Dependabot recreated it), use `gh pr view 349 --repo cognitiveghost/shopify-fulfillment-tool --json headRefName`
for the new ref.

- [ ] **Step 2: Build the throwaway venv with the system 3.14**

`/usr/bin/python3.14` is the interpreter whose `venv` ships pip on this VM. Bare `python3` may not.
```bash
/usr/bin/python3.14 -m venv <JOBTMP>/venv349
```
```bash
<JOBTMP>/venv349/bin/python -m pip install -q -r <JOBTMP>/pr349/requirements.txt -r <JOBTMP>/pr349/requirements-dev.txt
```
Expected: exit 0. `<JOBTMP>/venv349/bin/python -m pip show numpy pandas | grep -E '^(Name|Version)'` shows
numpy 2.5.x and pandas 3.0.x.

- [ ] **Step 3: Run the CI gate exactly as the `verify` job does, from the worktree root**

```bash
<JOBTMP>/venv349/bin/ruff check . --exclude shared
```
```bash
CI=1 QT_QPA_PLATFORM=offscreen <JOBTMP>/venv349/bin/python run_dev.py
```
```bash
QT_QPA_PLATFORM=offscreen <JOBTMP>/venv349/bin/python -m pytest -q
```
Expected: ruff "All checks passed!", the smoke test exits 0, and pytest reports 0 failed. Record the pytest summary
line (e.g. `NNNN passed, M skipped`) for the PR body.

**If anything fails:** stop. Do not edit requirements or code. Use superpowers:systematic-debugging only to name the
package and error, `runner <run> note` it, and hand back to the owner. A package incompatibility is a new decision.

- [ ] **Step 4: Remove the throwaway venv**

```bash
rm -rf <JOBTMP>/venv349
```

---

### Task 2: Move CI and the release build to Python 3.14

**Files:**
- Modify: `.github/workflows/build_release.yml`, the three `python-version: '3.11'` lines (in jobs `verify` ~L39,
  `version` ~L98, `build` ~L129).
- Modify: `README.md:23`.

**Interfaces:**
- Consumes: Task 1 verdict = pass.
- Produces: commit on `dr/6-bump-the-python-group-goes-with-error` that Task 3 pushes.

- [ ] **Step 1: Show the failing condition**

```bash
grep -n "python-version" .github/workflows/build_release.yml
```
Expected: three lines, each `python-version: '3.11'`.

- [ ] **Step 2: Edit the workflow**

Replace every `python-version: '3.11'` with `python-version: '3.14'` (Edit tool, `replace_all: true`). No other
change in the file. The `uses: actions/setup-python@v5` lines stay as they are; #348 owns them.

- [ ] **Step 3: Edit the README**

`README.md` line 23, exact old text:
```
Python 3.14 on the dev machine; CI and release builds use 3.11.
```
New text:
```
Python 3.14 on the dev machine, in CI and in release builds.
```

- [ ] **Step 4: Verify**

```bash
grep -rn "3\.11" .github/workflows/ README.md
```
Expected: no output.
```bash
grep -c "python-version: '3.14'" .github/workflows/build_release.yml
```
Expected: `3`. `/usr/bin/git diff --stat` shows exactly 2 files, 4 insertions, 4 deletions. The workflow's YAML
shape is unchanged, since only values inside existing quotes change. CI parses it in Task 3.

- [ ] **Step 5: Run the repo gate** (sanity only; the change touches no Python)

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```
```bash
.venv/bin/ruff check . --exclude shared
```
Expected: 0 failed; "All checks passed!".

- [ ] **Step 6: Commit**

Write `<JOBTMP>/commit-msg.txt`:
```
ci: run CI and release builds on Python 3.14

numpy 2.5 needs Python >= 3.12, so Dependabot #349 (python group) failed
at pip install on the 3.11 pin before any test ran. 3.14 matches the dev
VM and has the longest SPEC 0 runway; every compiled dependency ships a
win_amd64 wheel for it.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```
(Use the attribution lines your own session's system reminder gives, if they differ.)
```bash
/usr/bin/git add .github/workflows/build_release.yml README.md
```
```bash
/usr/bin/git commit -F <JOBTMP>/commit-msg.txt
```

---

### Task 3: Open the fix PR with the Windows build, and verify #348

**Files:** none in the repo.

**Interfaces:**
- Consumes: Task 2 commit; Task 1 pytest summary line.
- Produces: fix PR number/URL (report it with `runner <run> pr cognitiveghost/shopify-fulfillment-tool <n> <url>`).

- [ ] **Step 1: Bring the branch up to date with `origin/main`**

```bash
/usr/bin/git fetch origin
```
```bash
/usr/bin/git rebase origin/main
```
If #348 already merged, `build_release.yml` conflicts on neighbouring lines. Resolve by keeping #348's `@vN` action
versions and this branch's `'3.14'`. Re-run Task 2 Step 4's greps, then `/usr/bin/git rebase --continue`.

- [ ] **Step 2: Push**

```bash
/usr/bin/git push -u origin dr/6-bump-the-python-group-goes-with-error
```

- [ ] **Step 3: Open the PR with the `windows-build` label**

Write `<JOBTMP>/pr-body.md` with this content, filling the bracketed pytest line from Task 1:

```markdown
Moves CI (`verify`, `version`) and the Windows release build from Python 3.11 to 3.14.

**Why:** Dependabot #349 fails at `pip install` on every run: `No matching distribution found for numpy>=2.5.3`.
numpy 2.5 requires Python >= 3.12. 3.14 matches the dev VM and gives the longest SPEC 0 runway. Every compiled
dependency ships a win_amd64 wheel for it.

**Checked locally:** #349's exact requirement files in a fresh Python 3.14 venv: ruff clean, headless smoke test
OK, pytest [NNNN passed, M skipped].

**Windows:** labelled `windows-build`, so "Build Executable" freezes the exe on 3.14 and checks the bundled assets.

**After merging (owner):**
1. #348 (actions group) can merge before or after this. If it merges after, Dependabot rebases it itself.
2. Comment `@dependabot rebase` on #349 so its CI re-runs on 3.14.

Spec: `docs/superpowers/specs/2026-09-29-ci-python-314-dependabot-design.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```
(Use the PR attribution lines your own session's system reminder gives, if they differ.)

```bash
gh pr create --repo cognitiveghost/shopify-fulfillment-tool --base main --head dr/6-bump-the-python-group-goes-with-error --title "ci: run CI and release builds on Python 3.14" --body-file <JOBTMP>/pr-body.md --label windows-build
```
If `--label` is refused, add it with:
```bash
gh api -X POST repos/cognitiveghost/shopify-fulfillment-tool/issues/<N>/labels -f "labels[]=windows-build"
```

- [ ] **Step 4: Label #348 and record the review on it**

```bash
gh api -X POST repos/cognitiveghost/shopify-fulfillment-tool/issues/348/labels -f "labels[]=windows-build"
```
Write `<JOBTMP>/pr348-comment.md`:
```markdown
Release notes reviewed against how `build_release.yml` uses each action. There are no breaking changes that affect us:

| Action | Bump | Breaking change | Affects us? |
|---|---|---|---|
| checkout | v4→v7 | Node 24; creds in separate file; v7 blocks fork checkout under `pull_request_target`/`workflow_run` | No |
| setup-python | v5→v7 | Node 24; `pip-install` input removed | No (unused) |
| upload-artifact | v4→v7 | Node 24; ESM; optional `archive` input | No |
| download-artifact | v4→v8 | v5 path change for downloads **by ID**; v8 errors on digest mismatch | No (by name, same run) |
| attest-build-provenance | v2→v4 | Wrapper over `actions/attest` | No (`subject-path` kept; perms already set) |

Labelled `windows-build` to exercise upload-artifact v7 on the Windows job. download-artifact v8 and attest v4 run
only in the release job, so they are first exercised at the next release.
```
```bash
gh pr comment 348 --repo cognitiveghost/shopify-fulfillment-tool --body-file <JOBTMP>/pr348-comment.md
```

- [ ] **Step 5: Watch both PRs' checks to completion**

```bash
gh pr checks <N> --repo cognitiveghost/shopify-fulfillment-tool --watch
```
```bash
gh pr checks 348 --repo cognitiveghost/shopify-fulfillment-tool --watch
```
Expected on both: "Run Tests", "Check shared/ matches packing-tool", and "Build Executable" pass. Next Version and
Publish Release are skipped by design. The Windows build takes ~15 minutes. If "Build Executable" fails on the fix
PR, read `gh run view <run-id> --repo cognitiveghost/shopify-fulfillment-tool --log-failed`, note the failing
step and error with `runner <run> note`, and stop. Do not work around it.

- [ ] **Step 6: Report**

`runner <run> pr cognitiveghost/shopify-fulfillment-tool <N> <url>`, then one `runner <run> progress` line that
names the fix PR and says #348 is verified, and that `@dependabot rebase` on #349 is the owner's step after the
merge.
