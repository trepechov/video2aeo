# Video2AEO – project memory for Claude Code

This repo is the **video2aeo** Claude plugin ("Video2AEO"). Given the transcript of a new podcast/video
episode it produces an edited transcript, an AEO YouTube description with chapters, and a WordPress (Gutenberg)
article with the same title as the video and the video embedded as the first block – as text files the user pastes
by hand. Semi-automated: the agent drafts, humans approve at Gate A (facts, chapters, title) and once per output.

Content language is **Bulgarian**; code, comments and docs are English.

## Brand-neutral repo (do not break)
- No real brand data in commits: no channel/company names, people, site URLs, promo text, brand glossary or real
  episodes. Brands live in `~/.video2aeo/` on the user's computer (`brand.json`, `glossary.json`, `guidelines.md`,
  `config.json`); `config/` holds generic defaults with `{{PLACEHOLDERS}}`.
- Developer brand files and the pre-neutral snapshot live in git-ignored `private/` (see `private/BRAND-NOTES.md`).
  Read them for context; never copy their content into tracked files.
- No example folders are kept in the repo; tests build a fictional episode on the fly (`dev/fixture.py`).

## Read first
- `docs/plugin-build-plan.md` – architecture, instruction layers, roadmap (phase 1a manual MVP → 1b automation → phase 2 WordPress plugin → phase 3), decisions.
- `instructions/` – the general instructions, one file per output: `aeo-rules.md`, `youtube-description.md`, `wordpress-article.md`, plus `episode-schema.md` (`work/episode.json`, the single source of truth).

## Layout
- `.claude-plugin/plugin.json` – manifest (plugin name `video2aeo`; commands are `/video2aeo:<skill>`).
- `skills/` – `doctor`, `episode` (`/video2aeo:episode`: transcript → knowledge map → YouTube description), `resume` (continue after a crash, from `episode_status`), `wp-article`, `setup`. Each output command renders only its own file (`outputs` arg of `render_package`/`validate_package`).
- `agents/` – `transcript-editor`, `knowledge-mapper`, `aeo-reviewer`. Frontmatter `description` must be a YAML block scalar (`|`).
- `.mcp.json` + `server/launch.sh` (finds Python via `server/find-python.sh`) + `server/server.py` – local stdio MCP server `video2aeo` (stdlib-only Python).
- `hooks/` – only a fail-open, Python-free SessionStart dependency check (`check-deps.sh`). Never add blocking `PreToolUse` hooks
  (`dev/release.sh` fails on them). `skills/doctor` (`/video2aeo:doctor`) diagnoses Python/Git without the helper.
- `scripts/aeo_lib.py` – parsing, rendering (description, Gutenberg, JSON-LD), validation, brand loading (`USER_DIR`,
  `VIDEO2AEO_HOME`). `scripts/aeo_pipeline.py` – transcript chunks, merge, `progress.json`, `episode_status` (state is derived from files). `scripts/aeo_net.py` – optional YouTube + WordPress network calls. `scripts/aeo.py` – CLI.
- Episode folders: one `episodes_root` (setup → `~/.video2aeo/config.json`) → `<series folder>/<yyyy-mm>-<series>-<nn>-<slug>/`;
  paths are built by `episode_path`, the session folder is checked by `workspace_status`, and the output tools refuse
  other locations (`aeo_lib`: `classify_workspace`, `check_episode_dir`; override `allow_outside_root`).
- `config/brand.json`, `config/glossary.json` – generic defaults, merged with `~/.video2aeo/` files. `config/models.json` – default model per delegated operation; the user may override via `models` in `~/.video2aeo/config.json` (default = plugin table, setup never asks).
- `dev/` – developer-only: WordPress block validator, `package.sh`, `release.sh` (checks + version bump), `smoke.py`
  (setup flow and footer/promo rendering against a temp `VIDEO2AEO_HOME`). Not shipped.
- Setup: every user-facing skill preflights with the `setup_status` tool; the `setup` skill interviews the user and
  writes `~/.video2aeo/` via `save_setup` (marker `setup.json`). Adjustable guideline ids live in
  `skills/setup/references/guideline-catalog.md`, `aeo-rules.md` tags and `ADJUSTABLE_GUIDELINES` – keep all three in sync.

## Principles (do not break)
1. LLM writes language; code enforces rules (YouTube limits, chapter rules, block markup, schema, number traceability).
2. Every output is rendered from `episode.json` – never hand-edit rendered files.
3. Nothing publishes automatically. WordPress push is optional, draft-only and requires the article approval (`gates.wordpress`).
4. Promo text comes only from the approved brand config; opinions and forecasts are always attributed.
5. General guidelines ship with the plugin; brand/user instructions come from `~/.video2aeo/guidelines*.md` and may
   extend or override them, but never the code-enforced rules.
6. No top-level `bin/` folder (claude.ai refuses such plugins). Agents, hooks and local MCP only load in Claude Code mode of the desktop app (Cowork no longer exists) or in the CLI.
7. Runtime Python must stay stdlib-only and run on Python 3.9 (youtube-transcript-api / yt-dlp are optional, imported lazily).
   They are installed only through the `install_subtitle_tools` tool, after the user's yes (setup step 0 / `fetch_transcript` `can_auto_install`) – never silently.

## Dev environment
Develop here in Claude Code on the local Mac (repo root = plugin root); test the installed plugin in the Claude desktop
app. Claude Code loads skills, agents and the local MCP server via `--plugin-dir`, so iterate here; use the Desktop app in Code mode
for install/runtime checks. Opening Claude Code in the repo without `--plugin-dir` also tries `.mcp.json` as a project
server and fails (`${CLAUDE_PLUGIN_ROOT}` unset) – that is expected.

## Checks to run after any change
```bash
claude plugin validate .
python3 dev/smoke.py && /usr/bin/python3 dev/smoke.py                                          # setup, render + validate on the fictional fixture (3.14 and 3.9)
(cd dev && npm i && npm run validate-blocks)                                                  # expect invalid: 0, first block core/embed
grep -rniIf private/brand-terms.txt --exclude-dir={.git,private,node_modules,episodes} --exclude=package-lock.json .   # expect no output
```
Iterate in Claude Code: `claude --plugin-dir .`

## Test in Claude Desktop
1. Bump `version` in `.claude-plugin/plugin.json` (Desktop may keep a stale copy of the same version).
2. `dev/package.sh` → `dist/video2aeo-<version>.plugin` (until the GitHub marketplace is set up).
3. Desktop → Settings → Plugins: remove the old plugin, upload the new file (or push and click Update).
4. Switch the app to **Code** mode (toggle top left), new environment with a working folder → `/video2aeo:episode` + transcript `.txt` (plain chat loads skills only).

The desktop app runs `.mcp.json` (`sh server/launch.sh`) with the GUI PATH; the launcher picks the first working Python >= 3.9 of
`python3`, `python`, `py -3` (on this Mac `/usr/bin/python3`, 3.9, not Homebrew's 3.14). On Windows `sh` comes from Git for Windows.

## Status (22 Oct 2026)
v0.1 moved from a cloud session to the local Mac and made brand-neutral (plugin named `yt-aeo`). 0.4.0 renamed it to **Video2AEO** (`video2aeo`, settings `~/.video2aeo/`); the code still reads
the legacy `~/.yt-aeo/` folder and `YT_AEO_HOME` when the new ones are missing. 0.5.0 added episode formats: `brand.format` +
`brand.formats.<id>` profiles asked one question at a time in setup, a length-based coverage plan (`coverage_plan`), and
teaser/boilerplate markers in the edited transcript.
0.6.0 added the episodes root + series folders + workspace check (see `docs/plans/2026-10-22-001-…`).
0.8.0 made Windows installs work: `sh server/launch.sh` finds `python3`/`python`/`py -3`, a fail-open SessionStart check, `/video2aeo:doctor`,
Git for Windows documented as a requirement, Code mode (not Cowork) as the only route. First Windows run (2 Nov 2026): Git's default install leaves `sh` off the PATH, so the helper did not start; 0.8.1 adds `server/path-check.ps1` / `fix-path.ps1`
(registry-PATH check in the SessionStart hook and `/video2aeo:doctor`, fix only with the user's OK), `read_setup_bundle` (import an earlier install from a folder/zip)
and `unrecognised_keys` in `save_setup`. A single `.mcp.json` cannot avoid `sh` on Windows (no per-OS keys; only `${VAR}`/`${VAR:-x}` expansion).
0.8.2: the subtitle downloader is part of setup (`check_environment.missing_subtitle_tools` / `install_command`, `install_subtitle_tools`; `fetch_transcript` runs yt-dlp as `python -m yt_dlp` so a Windows pip install works, and returns `can_auto_install`).
Fixture render/validate ok on Python 3.14 and 3.9; 65 Gutenberg blocks, 0 invalid. **Not yet tested:** agents + MCP in
Desktop Code mode (incl. whether `pwd` matches the server's path in `workspace_status`), live `fetch_transcript`, `wp_push_draft`.

## Next steps (full list: `docs/plugin-build-plan.md` §3)
1. Publish on GitHub + marketplace; install in Desktop from it.
2. Phase 1a manual MVP: first brand folder in `~/.video2aeo/`; transcript `.txt` → text files, end to end in Code and Desktop; 5 back-catalogue episodes; freeze `episode.json` v1.0.
3. `claude plugin eval` suite in `evals/` (excluded from the package).
4. Phase 1b: automatic subtitles, credential hardening, human-run gate sign-off, HTML allowlist, then WP draft push.
5. Phase 2: WordPress plugin „Video2AEO for WordPress“ (see plan).
