---
title: "fix: Smooth Windows install, Python launcher, per-session dependency check"
type: fix
status: active  # 0.8.0: units 1-8 implemented; follow-up cleanup in 2026-11-02-002; Windows retest pending
date: 2026-11-02
target_version: 0.8.0
---

# fix: Smooth Windows install, Python launcher, per-session dependency check

## Summary

A first Windows install (Windows 10 LTSC, Claude desktop app, no Python/Git) failed in three layers: the helper
(MCP server) and the checks are started with a hard-coded `python3`, which the python.org installer never creates on
Windows; Git for Windows (Git Bash) is a hidden requirement; and nothing tells the user what is wrong, because the
only environment check (`check_environment`) lives inside the helper that cannot start. A second complaint: it worked
once and later "the Python path was missing again". Fix: a launcher that finds Python on any OS, a dependency check
that runs without Python and fails open, a Windows section in the docs, and a first-use instruction to work in Claude
Code mode.

## Findings from the repo

- `.mcp.json` hard-codes `"command": "python3"`. This is the only place the plugin itself starts Python.
- **The repo ships no hooks.** `write_guard.py` and `secret_guard.py` (named in the report) are not in the plugin
  (no `hooks/`, no match in any tracked file) and not in `~/.claude/settings.json` here. They come from somewhere
  else on that Windows machine (another plugin or a user/project settings file). See Open question 1.
- The setup skill (`skills/setup/SKILL.md` §0) already explains Python by OS, but only after the helper fails, and its
  Windows tip ("an admin changes `.mcp.json` to `python`") means editing a plugin file by hand.
- README says "Python 3.9+ (preinstalled on macOS)", nothing on Windows or Git.
- Constraints that stay: no top-level `bin/` (principle 6), runtime stays stdlib-only on Python 3.9 (principle 7).

## Requirements

- R1. On Windows, macOS and Linux the helper starts if any of `python3`, `python`, `py -3` is a working Python ≥ 3.9.
- R2. If no Python is found, nothing unrelated is blocked and the user gets a clear message with the fix.
- R3. At the start of every session a cheap check reports missing or changed dependencies (Python, and on Windows
  Git Bash) before the user hits a cryptic failure.
- R4. Git for Windows (Git Bash) is a documented Windows requirement, with the install steps.
- R5. The first-use instruction tells the user to switch the Claude desktop app to **Claude Code** mode (toggle at the
  top left), create a new environment and choose the folder to work in.
- R6. The check and the launcher are stdlib/POSIX-shell only and never need the dependency they are checking.

## Implementation units

### 1. Launcher that finds Python (R1, R6)

Replace the bare `python3` call with a small wrapper under `server/` (not `bin/`). It tries, in order, `python3`,
`python`, `py -3`; skips the Microsoft Store stub (a `python.exe` that only opens the Store: detect by running
`-c "import sys; print(sys.version_info[:2])"` and requiring ≥ 3.9); caches nothing, so it survives the interpreter
moving. On failure it prints one readable line to stderr (what is missing, link, "restart the Claude app").

How `.mcp.json` calls the wrapper is the one technical risk – the plugin manifest has a single command for all OSes.
Candidates, to be settled by a short spike on the Windows machine (**before** other work):

| Option | Mac/Linux | Windows | Risk |
|---|---|---|---|
| A. `command: "sh"`, `args: [launch.sh]` | works | needs `sh` on the GUI PATH; Git for Windows adds only `Git\cmd` by default, not `usr\bin` | may fail without Git PATH tweak |
| B. `command: "node"` + `launch.js` | needs Node | needs Node | adds a dependency – rejected unless the app bundles it |
| C. Keep `python3`, make Windows get one (Microsoft Store Python installs `python3.exe`; or `py` alias copy) | unchanged | install-path dependent, fragile | pushes the problem back on the user |
| D. Absolute Git Bash path via env var | – | `CLAUDE_CODE_GIT_BASH_PATH` may not be expanded in `.mcp.json` | unknown |

**Decision (2 Nov 2026):** option A. On the Windows machine `where sh` and `where bash` both resolve to
`C:\Program Files\Git\usr\bin\` (default Git for Windows install), so `command: "sh"` works from a normal shell.
Remaining risk: the Claude app may start with a different PATH than Command Prompt. Verified by installing the 0.8.0
test build; if the helper does not connect, fall back to D/C. The Windows docs (unit 4) must tell users to keep the
default Git options so `usr\bin` stays on PATH.

### 2. Dependency check that does not need Python (R2, R3, R6)

Add `hooks/hooks.json` with a **SessionStart** hook running a POSIX-shell script (`hooks/check-deps.sh`):

- Looks for a working Python ≥ 3.9 the same way as the launcher (shared snippet, one place).
- On Windows also checks that Git Bash is the shell running it (if the hook runs, Git Bash exists; if Git is missing
  the hook cannot run – so the setup/README/doctor path covers that case, see unit 4).
- Prints a one-line status and, when something is missing, the exact fix. Output goes to the session as context, so
  Claude can tell the user in plain words.
- **Always exits 0** (fail-open): a missing dependency must never block tool calls (R2 and report item 4.2).
- Fast (< 1 s), no network, no writes.

Hooks that ship in this plugin must be fail-open and Python-free; the plugin will not add `PreToolUse` guards.

### 3. In-session check as a fallback (R3)

- `episode`, `resume`, `wp-article` already preflight with `setup_status`; when the tool is missing they route to
  `setup`. Make that route explicit: "tool missing → `/video2aeo:doctor`" instead of an interview.
- New small skill `/video2aeo:doctor` that works **without** the helper: uses the Bash tool to run the same detection
  as unit 2 and prints a ✅/❌ checklist (Python, Git Bash on Windows, Python path), plus the fix per OS. Setup §0
  points to it. (If the environment has no Bash tool at all, the skill falls back to telling the user the install
  steps in text.)
- Once the helper runs, `check_environment` additionally reports `python.executable` so a changed path ("Python path
  missing again") is visible next to the last known value (see unit 5).

### 4. Windows requirements and install steps (R4)

README and `skills/setup/SKILL.md` §0 get a Windows section:

1. Python 3.9+ from python.org – tick **Add python.exe to PATH** (or install from the Microsoft Store).
2. Git for Windows (includes Git Bash) from git-scm.com – default options.
3. **Restart the Claude app** (PATH is read at start).
4. Then the first-use instructions (unit 6).

Remove the "admin edits `.mcp.json`" workaround. Add the requirements table (Python, Git/Git Bash on Windows) to the
top of the README setup, mirrored in `docs/plugin-build-plan.md` §constraints.

### 5. Why "it worked, then the Python path was missing" (R3)

Likely causes to confirm on the user's machine: Python installed per user and PATH not reaching the GUI app after a
restart/update; Store `python.exe` alias taking precedence; Python upgraded/uninstalled. Mitigation: the launcher
re-detects on every start (no cached path); the SessionStart check shows which interpreter was found. Optionally store
`last_python` in `~/.video2aeo/` and warn when it changes. Needs the user's reproduction details (Open question 3).
**Update (2 Nov 2026, review):** `last_python` was removed again – the hook runs under a different PATH than the helper
(CLI vs desktop app, doctor via the Bash tool), so it raised false "Python changed" warnings and broke the hook's
no-writes rule. The helper's own interpreter is shown by `check_environment.python.executable` instead.

### 6. First-use instruction: Claude Code mode (R5)

Wording for README, `setup` skill intro and the doctor output:

> After installing the plugin, switch the Claude desktop app to **Claude Code** mode (toggle at the top left),
> create a **new environment** and choose the folder you want to work in (your episodes folder). Then run
> `/video2aeo:episode`.

Cowork mode no longer exists in the desktop app: the top-left toggle now has **Claude** (chat) first and **Code**
second. Because the plugin runs many scripts (helper, hooks, agents), Code mode is the only supported route, and every
entry point says so. Plan:

- Replace every "Cowork task" mention (README, `.claude/CLAUDE.md` "Test in Claude Desktop", setup skill, `episode`
  skill, `docs/plugin-build-plan.md`) with the Code-mode instruction above.
- The SessionStart check and `/video2aeo:doctor` tell the user to switch to Code mode when they appear to be in plain
  chat (skills load there but the helper and agents do not).
- The exact UI labels are taken from the user's current app version; confirm them during review.

### 7. Tests and checks

- `dev/smoke.py`: add a launcher test with `python3` absent from PATH (fake PATH containing only `python`), and with
  only a "Store stub" that exits non-zero.
- Shell script tests for `check-deps.sh` (found / not found / old version → exit 0 in every case).
- `claude plugin validate .`, existing smoke on 3.14 and 3.9, block validator, brand-term grep (unchanged checks).
- `dev/release.sh`: fail if `hooks/hooks.json` contains a `PreToolUse` entry or any `*_guard.py` is tracked.
- Manual: fresh Windows VM or the report machine, with and without Python, with and without Git.

### 8. Release

Bump to 0.8.0, `dev/package.sh`, reinstall on the Windows machine. Record in CLAUDE.md status and the plan docs.

## Order of work

1. Spike on Windows: unit 1 options A/D (decides `.mcp.json`).
2. Units 1 + 2 (launcher, SessionStart check).
3. Units 3, 4, 6 (doctor skill, docs, first-use text) – mostly text.
4. Unit 7 tests, unit 8 release, retest on the Windows machine.

## Open questions for you

1. ~~Where do `write_guard.py` / `secret_guard.py` come from?~~ **Resolved:** not from this repo. Searched the
   working tree, full git history (`git log -S`), `.claude/`, `private/` and the old `dist/` package: no guard scripts,
   no `PreToolUse` hooks, nothing to remove. They live in another plugin or settings file on the Windows machine
   (check `/hooks` there). Unit 7 adds a release check that fails if a tracked file defines blocking hooks.
2. ~~Is Claude Code mode the supported route?~~ **Resolved:** yes, Cowork is gone; Code mode is the only route (unit 6).
3. ~~When did "Python path missing again" happen?~~ **Answered:** not after a restart; cause unknown. Unit 5 stays: re-detect on every start and show the interpreter found at session start; add `last_python` tracking to diagnose it if it recurs.
4. ~~Run `where sh` / `where bash`~~ **Answered:** both found in `Program Files\Git\usr\bin` -> option A.

## Out of scope

Bundling Python with the plugin, a Node-based server rewrite, automatic installation of Python/Git (a silent installer
would be a separate, consent-gated feature).
