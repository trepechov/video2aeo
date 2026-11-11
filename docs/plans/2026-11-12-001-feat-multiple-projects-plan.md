---
title: "feat: Multiple projects – one settings folder per project, stored where the user chooses, automatic upgrade of the single-project setup"
type: feat
status: active – decisions confirmed by the user on 12 Nov 2026
date: 2026-11-12
origin: user request of 12 Nov 2026 (several projects on one computer; settings inside a monorepo; no lost settings for 0.9 users)
---

# feat: Multiple projects with a chosen settings location

## Summary

Today every setting lives in one folder, `~/.video2aeo/` (or `VIDEO2AEO_HOME`), read once when the helper starts.
One computer can therefore serve exactly one brand. This plan makes the plugin work with **several projects** – each
with its own brand, glossary, guidelines, formats, models, episodes folder and WordPress sign-in – and lets the user
decide **where each project's settings are stored**:

- **in the project folder** (`<project>/.video2aeo/`, e.g. inside a monorepo, committed with the code),
- **in the user profile** (`~/.video2aeo/projects/<id>/`, private, as today), or
- **in any folder the user picks** (e.g. `<monorepo>/config/video2aeo/<show>/`).

The active project is found automatically from the folder the session is opened in, the same way `git` finds its
repository. Existing 0.9 users are upgraded automatically on first start: their settings become the first project,
in the profile, with the same episodes folder – nothing to answer, nothing lost, and the old files left exactly where
they are.

---

## Problem Frame

- A marketer or agency working for two shows/brands has to swap folders or restart the app with another
  `VIDEO2AEO_HOME` – not something a non-developer can do, and easy to get wrong (a promo block of brand A published in
  brand B's description).
- A developer team keeps its podcast tooling in a monorepo and wants the brand setup versioned next to the code, so a
  colleague who clones the repo gets the same brand, glossary and guidelines without the setup archive.
- `USER_DIR` is a module constant (`scripts/aeo_lib.py:34`) used in ~40 places (`aeo_lib`, `aeo_setup`, `aeo_net`,
  `dev/smoke.py`); skills, agents and instructions name `~/.video2aeo/…` paths directly (~25 places).
- The single MCP server process lives for the whole session; it cannot learn the project from its start-up
  environment – the project must be resolved per call.

**Success:**
1. Two projects on one Mac, one in a monorepo and one in the profile; opening a session in either folder runs
   `/video2aeo:episode` with that project's brand, without any question.
2. A colleague clones the monorepo, opens the project folder and only answers the computer-specific questions.
3. A 0.9 user installs the new version and runs `/video2aeo:episode` exactly as before; `setup_status` shows one
   project with their old values; a backup of the old folder exists.

---

## Terms (used in the skills and UI, in plain words)

| Term | Meaning |
|---|---|
| **Project** | One brand/show set-up: brand, glossary, guidelines, formats, models, episodes folder, WordPress sign-in. Has an `id` (slug) and a display name. |
| **Project folder** | The folder the user opens the session in for that project (a repo package, or the episodes folder). Used to find the project. |
| **Settings folder** | Where the project's team files are stored: inside the project folder, in the profile, or a custom folder. |
| **User folder** | `~/.video2aeo/` (or `VIDEO2AEO_HOME`): this computer's list of projects, sign-ins, subtitle tools. Never shared. |

---

## Requirements

- R1. Any number of projects on one computer; each has its own team files and its own episodes folder and WordPress
  sign-in. Nothing of one project is ever read while another is active.
- R2. When creating a project, setup asks one friendly question – where to keep its settings – with three answers:
  in the project folder (recommended when the folder is a git repository), in my user profile (recommended otherwise),
  or a folder I choose. The choice can be changed later („премести настройките“) without losing anything.
- R3. The active project is resolved automatically from the session folder (or from the episode folder a tool gets).
  Only when it is ambiguous (no match, several candidates) does the skill ask once which project to use.
- R4. Settings stored inside a project folder or custom folder hold **only team files** – never passwords, cookies or
  computer-specific paths – so they are safe to commit. Sign-ins stay in the user folder, per project.
- R5. Several projects in one monorepo (e.g. `apps/show-a/.video2aeo/`, `apps/show-b/.video2aeo/`): the nearest one
  above the session folder wins.
- R6. Settings found in a folder that this computer has not used before (a fresh clone) are shown for review once
  before the agents follow them – the same review as importing a colleague's archive (guidelines and published text in
  full) – then remembered.
- R7. **Backward compatibility:** a 0.9 user folder (flat `brand.json`, `glossary.json`, `guidelines.md`,
  `guidelines/`, `setup.json`, `config.json`, `backup-*/`) is converted automatically, once, into the new layout as the
  computer's first project, in the profile, linked to the saved episodes folder. Every value is kept (brand, glossary,
  guidelines, switched-off guidelines, formats, models, episodes folder, WordPress and YouTube settings). The original
  files stay where they are, unchanged (a downgrade to 0.9 keeps working). A failed or interrupted conversion leaves the
  plugin working as before.
- R8. Existing episode folders keep working (resume, render, validate) without being moved or edited.
- R9. The setup archive (`export_setup` / `read_setup_bundle`) works per project; archives from 0.9 import unchanged;
  an archive can create a new project.
- R10. No regressions of the standing principles: stdlib-only Python 3.9, nothing published automatically, promo only
  from approved config, brand-neutral repo, fail-open hook, no blocking hooks, no `bin/`.

---

## Key Technical Decisions

### 1. New layout

```
~/.video2aeo/                      user folder – this computer only, never shared, never committed
  projects.json                    list of projects known on this computer (see below)
  config.json                      computer-wide: youtube cookies settings (unchanged key)
  credentials/<id>.json            per project: wordpress {base_url, username, app_password} (mode 600)
  projects/<id>/                   settings folders stored "in the profile"
  last_python, tools-venv/         unchanged (computer-wide)
  brand.json, glossary.json, …     0.9 flat files: left in place after conversion, no longer read (see decision 5)
  MOVED-TO-PROJECTS.txt            written at conversion: where the settings now live

<settings folder>/                 any of the three locations – team files only, safe to commit
  project.json                     id, name, settings format version, models, guidelines_off*, episodes_root (optional, relative)
  brand.json  glossary.json  guidelines.md  guidelines/*.md  setup.json
  .gitignore                       written by setup: backup-*/, *.bak, *.broken
  backup-<timestamp>/              import/replace backups (as today, ignored by git)

<project folder>/.video2aeo/       either IS the settings folder (location "project"),
  location.json                    or holds only this pointer: {"settings_dir": "../../config/video2aeo/show-a"} (relative)
```

`projects.json`:
```json
{"version": 1,
 "default": "show-a",
 "projects": {
   "show-a": {"name": "Show A", "settings_dir": "/Users/x/.video2aeo/projects/show-a", "location": "profile",
              "folders": ["/Users/x/Podcasts/Show A"], "episodes_root": "/Users/x/Podcasts/Show A",
              "trusted": "2026-11-12T10:00:00"}}}
```
(`*` `guidelines_off` stays in `setup.json` where 0.9 keeps it; listed only to show it is a team value.)

*Rationale:* team files and computer files are already separated in 0.9's export whitelist (`config.json` holds both
models and passwords). Splitting them on disk makes the in-repo option safe by construction (R4) and keeps the
archive code almost unchanged. Profile-stored projects use the very same folder format, so moving a project between
locations is a folder copy plus a pointer update.

### 2. How the active project is found (one function, `resolve_project(path)`)

Checked in this order; the first hit wins; the result says how it was found (`found_by`):

1. `VIDEO2AEO_PROJECT` environment variable – a settings folder; for headless/dev runs only.
2. **Walk up** from the given path (episode folder if the tool has one, else the session folder): the nearest
   `.video2aeo/` that holds `project.json` (settings here) or `location.json` (settings there). Stops at the user's home
   folder and the disk root. This is what makes a monorepo clone work for every teammate without any registration.
3. **This computer's list** (`projects.json`): the project whose `folders` or `episodes_root` contains the path
   (longest match wins). This is how profile-stored and custom-folder projects outside a repo are found.
4. **Only one project** known → that one (keeps a single-project user's experience exactly like 0.9, whatever folder
   they open).
5. Otherwise **unresolved**: `setup_status` returns `project: null` and the list of projects; the skill asks once
   (AskUserQuestion with the project names, plus „Нов проект“) and passes the choice back.

`VIDEO2AEO_HOME` keeps its meaning – the user folder – so the dev checks and power users are unaffected.

### 3. Per-call project context in the server

`USER_DIR` disappears as a constant. A small `Project` object (`id`, `name`, `settings_dir`, `user_dir`,
`credentials_path`, `episodes_root`, `found_by`, `location`) is resolved per tool call and passed explicitly to the
library functions that read settings (`load_brand(project)`, `setup_status(project)`, `save_setup(project, …)`,
`episodes_root(project)`, `_load_wp_config(project)` …). *Rationale:* explicit beats a hidden global – tests can run two
projects side by side, and a wrong-project read cannot happen silently.

How a call knows its path:
- every tool gets two optional arguments: `cwd` (the session folder, from `pwd`) and `project` (an id the user chose);
- tools with `episode_dir` resolve from the episode folder (so resume/render always use the episode's own project,
  whatever the session folder);
- the server **remembers the project of the first successful `setup_status`** for the rest of the session and uses it
  when a later call has neither `episode_dir` nor `cwd`; a call whose `episode_dir` resolves to a different project than
  the remembered one fails with `project_mismatch` (name both) instead of mixing brands.
- fallback when nothing is given: the server's own `os.getcwd()` (works in the CLI; Desktop to be probed – see open
  questions).

### 4. Where-to-store question (setup, new project)

One *choice* question, asked only when a project is created or moved:

„Къде да пазим настройките на този проект?“
- **В папката на проекта** – `<project folder>/.video2aeo/` · „подходящо за git хранилище: колегите получават
  настройките с кода; пароли там никога не се записват“ (recommended when the session folder is inside a git repo)
- **В моя потребителски профил** – `~/.video2aeo/projects/<id>/` · „само на този компютър, както досега“
  (recommended otherwise)
- **В папка, която избирам** – then a text question for the path (absolute or relative to the project folder),
  e.g. `config/video2aeo/show-a` in a monorepo. If that folder is inside the same repository as the project folder,
  setup also writes `<project folder>/.video2aeo/location.json` with the relative path, so teammates find it after a
  clone; otherwise it is recorded only in this computer's list.

Every answer is shown with the exact resulting path before saving. Setup never writes into a folder that already holds
another project's settings and never writes outside the chosen folder (plus the pointer file). The project folder
defaults to the session folder; the episodes folder question follows (as today), with an extra suggestion
`<project folder>/episodes` for repo projects – stored relative in `project.json` when it is inside the repository,
otherwise in this computer's list.

### 5. Automatic conversion of a 0.9 user folder (backward compatibility)

Runs at the first tool call of the new version (any tool, before resolving), only when the user folder has a flat
`setup.json` or `brand.json` and no `projects.json`.

1. Take a lock (`.migrate.lock`, created exclusively) so two open sessions cannot convert at the same time; a stale
   lock (> 10 min) is ignored.
2. Choose the id: slug of `brand.channel`, else `default`.
3. Copy (never move first) into `projects/.<id>.tmp/`: `brand.json`, `glossary.json`, `guidelines.md`, `guidelines/`,
   `setup.json`, `backup-*/`, `guidelines.md.bak`, `*.broken`; write `project.json` with `models` from `config.json`.
4. Write `credentials/<id>.json` with `config.json`'s `wordpress` (mode 600); keep `youtube` in `config.json`;
   `episodes_root` goes into the project's entry in `projects.json`, together with `folders: [episodes_root]`.
5. Verify: every copied file reads back byte-identical; JSON files parse.
   (The WordPress password then exists twice on this computer – in the old `config.json` and in `credentials/<id>.json`,
   both mode 600, both only in the user folder. Accepted for downgrade safety.)
6. Rename `.<id>.tmp` → `<id>`, write `projects.json` (atomic) with `default: <id>`, `trusted` set (the user wrote
   these files themselves).
7. The original flat files are **left in place, unchanged** (user's decision, 12 Nov 2026): a downgrade to 0.9 keeps
   working, and they remain a full backup. Only `MOVED-TO-PROJECTS.txt` is added, saying in plain words where the
   settings now live and that changes made in the new version are not seen by 0.9. Once `projects.json` exists the new
   version never reads the flat files again (no double source of truth). `last_python`, `tools-venv/` and unknown
   files (e.g. a user's own `Archive.zip`) are not touched.
8. `setup_status` reports `migrated: {from: "0.9", project: <id>, old_files: <user folder>}` once (until the next save) and the
   skill tells the user in one sentence that the settings were moved and nothing changed for them.

Failure at any step before 6: remove the temp folder, release the lock (the flat files were never touched), keep
running on them exactly like 0.9 (a read-only *legacy* resolution path), report `migration_error` in `setup_status`, retry on the next start.
Because there is only one project after conversion, rule 4 of the resolution keeps every folder working as before;
the episodes folder check is unchanged. Existing episode folders need no edit (R8).

The conversion code is the only compatibility path; it stays for at least two minor versions and is covered by smoke
tests built from a 0.9-shaped fixture folder.

### 6. Trust of settings found in a folder (R6)

A settings folder found by walking up (rule 2) that is not in `projects.json` yet – typically a fresh clone – is not
used silently: `setup_status` returns `needs_review: true` with the folder; the setup skill runs the same review as an
archive import (channel, people, formats, then header/footer/promo, `guidelines.md`, `guidelines/*.md` in full) and on
the user's yes records the project (with `trusted` and the folder) in `projects.json` and asks only the computer
questions (episodes folder if not set in `project.json`, WordPress sign-in later on request). Later edits arriving via
git are the team's own and are not re-reviewed (user's decision): a user who wants to change something runs setup
(„промени настройките“).

### 7. Module placement

New `scripts/aeo_project.py` (stdlib only): `Project`, `resolve_project`, `projects.json` read/write, walk-up search,
pointer files, conversion, `create_project`, `move_project`, `list_projects`. `aeo_lib.py` loses `USER_DIR` and takes
a `Project` argument where it reads settings; `aeo_setup.py` and `aeo_net.py` likewise. Keeps `aeo_lib.py` from growing
past its current ~1,500 lines.

---

## Tools (`server/server.py`)

| Tool | Change |
|---|---|
| all tools | + optional `cwd`, `project`; result of settings-reading tools gains `project: {id, name, settings_dir, location, found_by}` |
| `setup_status` | + `project`, `projects` (list: id, name, location, settings_dir), `needs_review`, `migrated`, `migration_error`; `user_dir` stays (user folder) and `settings_dir` is new |
| `save_setup` | + `create: {id, name, location: project\|profile\|custom, settings_dir?, project_folder}` for a new project; writes team files to the settings folder, `episodes_root` to `project.json` (relative, in-repo) or `projects.json` |
| `list_projects` *(new)* | read-only list for the "which project?" question and „покажи проектите“ |
| `move_project` *(new)* | `id`, new `location`/`settings_dir`: copy → verify → switch pointer/list → old folder kept as `backup-moved-<ts>` (never deleted) |
| `trust_project` *(new)* | records a reviewed, walk-up-found settings folder in `projects.json` |
| `export_setup`, `read_setup_bundle` | per active project; import can target a new project (`save_setup(create=…, replace=true)`) |
| `workspace_status`, `episode_path`, guarded tools | use the resolved project's episodes root and brand; `project_mismatch` error as described |

`wp_push_draft` reads `credentials/<id>.json`; the `VIDEO2AEO_WP_*` environment fallback stays.

---

## Implementation Units

### U1. Project resolution and the new layout — `scripts/aeo_project.py`
**Goal:** `Project`, `resolve_project(path, project_id)`, `projects.json`, walk-up with `project.json`/`location.json`,
`create_project` for the three locations (+ `.gitignore` in the settings folder), `list_projects`, `move_project`,
`trust_project`. **Reqs:** R1–R5. **Deps:** none.
**Tests (smoke):** resolution order for each rule; nearest-wins in a two-project monorepo; pointer with relative path;
walk-up stops at home; longest-match in the list; single-project fallback; unresolved with two projects; custom folder
outside any repo; creating into a folder that already holds another project is refused; settings folder never
receives `wordpress`/cookies keys; move keeps the old folder and switches the pointer.

### U2. Automatic conversion of the 0.9 folder
**Goal:** section 5. **Reqs:** R7, R8. **Deps:** U1.
**Tests:** 0.9-shaped fixture (flat files, `config.json` with models + episodes_root + wordpress + youtube, `guidelines/`,
two `backup-*`, an unknown `Archive.zip`, `tools-venv/`) → every value readable through the new API, byte-identical
copies, credentials file mode 600, unknown files untouched, every original file byte-identical and still in place,
`MOVED-TO-PROJECTS.txt` written, flat files not read afterwards (edit one → no effect); second run is a no-op;
simulated failure after the copy leaves the flat folder intact and `setup_status` working (legacy path) with
`migration_error`; concurrent lock; an episode folder created under 0.9 renders and resumes after conversion;
`VIDEO2AEO_HOME` pointing to a flat folder is converted the same way.

### U3. Library refactor: no `USER_DIR`
**Goal:** every settings read/write in `aeo_lib.py`, `aeo_setup.py`, `aeo_net.py` takes a `Project`; export/import per
project; `setup_status` additions. **Reqs:** R1, R4, R9. **Deps:** U1.
**Tests:** existing smoke suite passes unchanged in behaviour against a single profile project; two projects in one run
never read each other's brand (render the fixture for both, compare footers).

### U4. Server
**Goal:** `cwd`/`project` arguments, per-call resolution, session binding, `project_mismatch`, new tools, updated
descriptions (no `~/.video2aeo/` wording where the settings folder is meant). **Reqs:** R3. **Deps:** U1–U3.
**Tests:** JSON-RPC calls in `dev/smoke.py` (as today's `workspace_status` call): bind via `setup_status(cwd)`, render
with an episode of another project → `project_mismatch`.

### U5. Setup skill
**Goal:** start of setup: show the active project (name + settings folder) or ask which one; routes „Нов проект“
(interview or archive) → where-to-store question (section 4) → existing steps; „Премести настройките“; „Покажи
проектите“; review of a found folder (section 6); one-sentence notice after conversion. Same one-question-per-message
style, pre-fill, Bulgarian examples. **Reqs:** R2, R3, R6, R9. **Deps:** U4.

### U6. Episode, wp-article, resume, doctor skills; agents; instructions
**Goal:** replace every `~/.video2aeo/…` path with "the settings folder (`setup_status.project.settings_dir`)"; preflight
passes `cwd`; the project name is said once at the start of a run („Проект: Show A“) so the user notices a wrong one;
agents receive the settings folder path from the orchestrator. **Reqs:** R1, R3. **Deps:** U4.

### U7. Docs and release
README (projects, the three locations, monorepo example, upgrade note: old files kept, downgrade possible), `CLAUDE.md`
layout/status, `docs/plugin-build-plan.md` decision entry (supersedes "one brand per `~/.video2aeo/`"),
`instructions/README.md`, guideline catalog wording. Version **0.10.0** (settings layout change). **Deps:** U1–U6.

### U8. Verification
Checks from `CLAUDE.md` (validate, smoke on 3.14 and 3.9, block validator, brand-term grep) plus: headless
`claude -p --plugin-dir .` runs with a temp `VIDEO2AEO_HOME` for (a) a 0.9 folder → upgrade → episode render, (b) new
project in a temp git repo (in-folder location) → second session from a "clone" → review → render, (c) custom folder in
a monorepo with two shows. Manual Desktop Code-mode check of the session folder seen by the server (was open question 1 – still to be probed).

---

## Risks

| Risk | Mitigation |
|---|---|
| Wrong project used → brand A's promo in brand B's description | project name shown at the start of every run; `project_mismatch` guard; explicit `Project` argument everywhere; two-project smoke test |
| Conversion loses or corrupts settings | copy-verify-switch, originals never modified, `MOVED-TO-PROJECTS.txt`, lock, idempotent, legacy fallback |
| Passwords committed to a repo | credentials never stored in settings folders (by code); `.gitignore` written for backups |
| Unreviewed instructions from a cloned repo | first-use review (section 6), like archive import |
| Downgrade to 0.9 after conversion | old files stay in place, 0.9 keeps working with the values of the conversion day |
| Two copies of the WordPress password | both only in the user folder, mode 600; documented in README |
| Desktop server cwd differs from the shell's `pwd` | skills always pass `cwd`; episode tools resolve from `episode_dir` |

---

## Decisions (confirmed by the user, 12 Nov 2026)

1. **Default location** for a new project outside a git repo: the user profile. (In a git repo the project folder is
   offered first.)
2. **0.9 files after conversion stay where they are**, unchanged; the new version stops reading them.
3. **No re-review on change.** Settings found in a folder are reviewed once on first use per computer; later changes
   (e.g. via `git pull`) are not re-reviewed – a user who wants different settings runs setup.
4. **Episodes folder inside the repo** may be stored relative in `project.json` and is shared with the team; otherwise
   it stays computer-specific in `projects.json`.
5. **Version 0.10.0.**
