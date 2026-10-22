---
title: "feat: Episodes root, series folders and workspace check"
type: feat
status: active
date: 2026-10-22
target_version: 0.6.0
---

# feat: Episodes root, series folders and workspace check

## Summary

Episode files must always land in one known place. Setup stores one `episodes_root`; each format profile gets a `folder`
slug; code builds `<root>/<series>/<episode>/` and refuses writes anywhere else. A new `workspace_status` tool lets the
skills notice a wrong session folder before anything is written, and stop with clear instructions.

## Problem Frame

The user often starts an episode task without selecting the working folder, so `episodes/…` is created in whatever folder
the session happens to run in. The plugin cannot choose the session folder (Cowork grants one at task start), so it can
only detect, confirm, remember and guard.

## Requirements

- R1. Setup saves one `episodes_root` (absolute path) in `~/.video2aeo/config.json`.
- R2. Each format profile has a `folder` slug (series folder). Base format with no profile uses `_other`.
- R3. Episode path is built by code: `<root>/<series>/<yyyy-mm>-<series>-<nn>-<slug>/`, with `work/` inside.
- R4. `workspace_status` classifies the session folder as `ok`, `inside_episode`, `suspicious`, `unknown` or `no_root`.
  Any state except `ok` / `inside_episode` stops the skill before the transcript is read.
- R5. `import_transcript`, `fetch_transcript`, `render_package`, `validate_package`, `wp_push_draft` accept only an
  `episode_dir` that is the exact built path or an existing episode (`work/episode.json`) under the root; otherwise an
  error names the expected path. An explicit override flag exists.
- R6. `episode` and `wp-article` print the absolute target path before the first write.
- R7. Existing episodes are untouched; resume works for any folder with `work/episode.json`.

## Scope Boundaries

- No migration helper for old episode folders. No auto-selection of the Cowork folder (not possible).
- Not in scope: a `/video2aeo:new` command, multiple roots, per-series roots outside the main root.

## Key Technical Decisions

- **Code owns paths and the guard.** Skill text is skippable; the tool-level guard is not (same reasoning as `require_setup`).
- **Skill passes its own cwd.** The MCP server's `os.getcwd()` may differ from the session folder, so `workspace_status`
  takes an optional `cwd` that the skill reads with `pwd`; the server falls back to its own cwd.
- **Missing root blocks, it does not warn.** After the upgrade, `setup_status.configured` stays true (so nobody is thrown
  back into the full interview); the guarded tools return `episodes_root_missing` pointing to the one setup question.
- **Series part of the episode name = the profile's `folder` slug**, so folder and name cannot drift apart.

## Data Needed to Implement

**Config (`~/.video2aeo/config.json`, other keys such as `youtube`/`wordpress` preserved)**

| Field | Type | Rule |
|---|---|---|
| `episodes_root` | absolute path string | must exist and be writable; stored resolved (`Path.resolve()`, `~` expanded) |

**Brand (`brand.json`)**: `formats.<id>.folder` – slug, `^[a-z0-9][a-z0-9-]{0,39}$`, unique across profiles, not `_other`;
validated in `save_setup` next to the existing `label` check. Optional for old profiles; a profile without `folder` falls
back to its `id` (documented, no breakage).

**Path rules**

- Episode folder: `<yyyy-mm>` from `upload_date` (fall back to today), `<series>` = series folder slug, `<nn>` = two-digit
  episode number, `<slug>` = ASCII slug of the title (Cyrillic transliterated or the user's short slug; max ~40 chars).
- Comparison on resolved paths (macOS `/private/tmp` symlinks, case-insensitive FS, Windows separators via `os.path.normcase`).
- `workspace_status` suspicious list: home directory itself, `Desktop`, `Downloads`, `Documents` (top level only), `/tmp`,
  `/private/tmp`, `/var/folders/*`, any path containing a `scratchpad` segment, filesystem root.

**New / changed tools (`server/server.py`)**

| Tool | Input | Returns |
|---|---|---|
| `workspace_status` | `cwd?` | `{ok, status, cwd, episodes_root, episode_dir?, series_folders[], reason, next_step}` where `status ∈ ok, inside_episode, suspicious, unknown, no_root` |
| `episode_path` | `format?`, `upload_date?`, `number?`, `slug` | `{ok, episode_dir, series_folder, created}`; creates series folder, episode folder and `work/`; `number` omitted = next free number in that series folder |
| `save_setup` | + `episodes_root?` | existing result; writes `episodes_root` into `config.json` (merge, atomic, mode preserved) |
| guarded tools (R5) | + `allow_outside_root?: bool` | on violation `{ok:false, wrong_folder:true, expected, got, error}` |

`setup_status.current` gains `episodes_root` and `series_folders` (`{profile id: folder}`).

**Open questions (answer before or during U1)**

1. **Cowork path mapping.** In Cowork the model's shell may see a sandbox path (e.g. a mounted folder) different from the
   host path the MCP server sees. Check in Desktop what `pwd` and the server's `os.getcwd()` return; if they differ,
   `workspace_status` must compare by folder name / mapping instead of absolute equality. *Needs a quick manual probe.*
2. **Real "bad" cwd samples** from past runs (what the random folder paths looked like) to tune the suspicious list.
3. **Episode number source:** auto next-in-series (proposed) vs. asking the user; does the show title already carry a number?
4. **Guard scope:** is `fetch_transcript` included (proposed yes, it writes) – confirm.
5. **Windows:** the server has just gained UTF-8 stream handling for Windows; is Windows a supported target for this feature
   (affects path normalisation tests)?

## Implementation Units

### U1. Library: config, path rules, classification, guard

**Goal:** All logic in one place, pure and testable. **Requirements:** R1–R5, R7.
**Dependencies:** none.
**Files:** `scripts/aeo_lib.py`, `dev/smoke.py`.
**Approach:** add `episodes_root()` reader (config.json), `series_folder(brand, profile)`, `build_episode_dir(...)`,
`next_episode_number(series_dir)`, `classify_workspace(cwd)`, `check_episode_dir(path, allow_outside_root)`; extend
`save_setup` validation and writing; extend `setup_status.current`. Follow existing patterns: `_write_atomic`,
`require_setup` style error dicts, stdlib-only, Python 3.9 syntax.
**Test scenarios:**
- Happy: root set, `cwd` = root → `ok`; `cwd` = `<root>/show-a` → `ok`; `cwd` inside an episode with `work/episode.json` → `inside_episode` with its path.
- Edge: `cwd` is a symlink to the root; trailing slash; case difference on macOS; root missing on disk.
- Error: `cwd` = home / Downloads / `/tmp` → `suspicious`; unrelated folder → `unknown`; no `episodes_root` → `no_root`.
- Guard: exact built path passes; sibling of root fails with `expected` in the message; legacy folder with `work/episode.json` outside root passes; override flag passes; path traversal (`<root>/show-a/../../x`) fails.
- `save_setup`: bad `folder` slug, duplicate slug, `_other`, non-writable root rejected; other `config.json` keys preserved.
- `next_episode_number`: empty series → 01; gaps and non-matching names ignored.
**Verification:** smoke checks pass on Python 3.14 and `/usr/bin/python3` (3.9).

### U2. MCP server: tools and guard wiring

**Goal:** Expose the logic. **Requirements:** R3–R5. **Dependencies:** U1.
**Files:** `server/server.py`, `dev/smoke.py`.
**Approach:** add the two tools to `TOOLS`; run the guard for the five path-taking tools after `require_setup`; add
`allow_outside_root` to their input schemas; update the `DIR` description to point to `episode_path`. Keep the
uncommitted UTF-8 stream change in `main()` intact.
**Test scenarios:**
- A guarded tool called with a wrong folder returns `wrong_folder` and writes nothing (directory listing unchanged).
- `episode_path` twice with the same inputs returns the same folder and does not renumber; without `number` it takes the next free one.
- JSON-RPC round trip of `workspace_status` through `handle()`.
**Verification:** `claude plugin validate .` passes; smoke passes.

### U3. Skills: setup interview and episode / wp-article preflight

**Goal:** The user is asked once, then only confirmed. **Requirements:** R1, R2, R4, R6. **Dependencies:** U2.
**Files:** `skills/setup/SKILL.md`, `skills/episode/SKILL.md`, `skills/wp-article/SKILL.md`.
**Approach:**
- setup: one question for the episodes root (suggest the current session folder) and one `folder` slug per format profile (suggest from the label), saved via `save_setup`; also a "change only this" path.
- episode / wp-article: after `setup_status`, run `pwd`, call `workspace_status(cwd)`. On `ok` continue silently; on `inside_episode` resume; on anything else stop and tell the user (one short message in Bulgarian) to reopen the task with the episodes root selected, or use the saved root where writable. In Step 0 replace the free-form "Episode folder" tree with `episode_path`, and print `📁 Saving to: <absolute path>` before the first write.
**Test scenarios:** `Test expectation: none -- prompt text; behaviour is covered by U1/U2 and a manual run below.`
**Verification:** manual run in Claude Code (`claude --plugin-dir .`) from a good and a bad folder, then in Desktop Cowork (also answers open question 1).

### U4. Docs, version, release checks

**Goal:** Ship 0.6.0. **Requirements:** all. **Dependencies:** U1–U3.
**Files:** `.claude-plugin/plugin.json`, `CLAUDE.md`, `docs/plugin-build-plan.md`, `skills/*/SKILL.md` (version metadata).
**Approach:** bump to 0.6.0 (skills' `metadata.version` in step); update the Layout / Status sections of CLAUDE.md and the plan
doc; keep the repo brand-neutral (fictional series slugs only). Run the full check list from CLAUDE.md, including the
block validator and the brand-terms grep. Commit directly on main (repo convention).
**Test scenarios:** `Test expectation: none -- documentation and version bump.`
**Verification:** all four checks from CLAUDE.md pass; `dev/package.sh` builds `dist/video2aeo-0.6.0.plugin`.

## Risks

| Risk | Mitigation |
|---|---|
| Cowork sandbox paths differ from host paths, making the guard reject valid folders | Open question 1 first; `allow_outside_root` override; compare by resolved path inside the server only |
| Existing users blocked right after upgrade | Clear `episodes_root_missing` message with the one-question setup path; `configured` unchanged |
| Over-aggressive "suspicious" list annoys users who work in Documents | Top-level folders only; list tuned from real samples (open question 2) |
