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
- Examples use the fictional demo brand in `examples/demo/`.

## Read first
- `docs/plugin-build-plan.md` – architecture, instruction layers, roadmap (phase 1a manual MVP → 1b automation → phase 2 WordPress plugin → phase 3), decisions.
- `instructions/` – the general instructions, one file per output: `aeo-rules.md`, `youtube-description.md`, `wordpress-article.md`, `facebook-post.md`, plus `episode-schema.md` (`work/episode.json`, the single source of truth).

## Layout
- `.claude-plugin/plugin.json` – manifest (plugin name `video2aeo`; commands are `/video2aeo:<skill>`).
- `skills/` – `episode` (`/video2aeo:episode`: transcript → knowledge map → YouTube description), `wp-article`, `fb-post`, `setup`. Each output command renders only its own file (`outputs` arg of `render_package`/`validate_package`).
- `agents/` – `transcript-editor`, `knowledge-mapper`, `aeo-reviewer`. Frontmatter `description` must be a YAML block scalar (`|`).
- `.mcp.json` + `server/server.py` – local stdio MCP server `video2aeo` (stdlib-only Python).
- `scripts/aeo_lib.py` – parsing, rendering (description, Gutenberg, JSON-LD), validation, brand loading (`USER_DIR`,
  `VIDEO2AEO_HOME`). `scripts/aeo_net.py` – optional YouTube + WordPress network calls. `scripts/aeo.py` – CLI.
- `config/brand.json`, `config/glossary.json` – generic defaults, merged with `~/.video2aeo/` files.
- `examples/demo/` – golden example (fictional brand + episode). Must stay valid.
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
6. No top-level `bin/` folder (claude.ai/Cowork refuse such plugins). Agents, hooks and local MCP only load in Cowork on the user's computer or in Claude Code.
7. Runtime Python must stay stdlib-only and run on Python 3.9 (youtube-transcript-api / yt-dlp are optional, imported lazily).

## Dev environment
Develop here in Claude Code on the local Mac (repo root = plugin root); test the installed plugin in the Claude desktop
app. Claude Code loads skills, agents and the local MCP server via `--plugin-dir`, so iterate here; use Desktop Cowork
for install/runtime checks. Opening Claude Code in the repo without `--plugin-dir` also tries `.mcp.json` as a project
server and fails (`${CLAUDE_PLUGIN_ROOT}` unset) – that is expected.

## Checks to run after any change
```bash
claude plugin validate .
export VIDEO2AEO_HOME=examples/demo
python3 scripts/aeo.py render examples/demo && python3 scripts/aeo.py validate examples/demo   # expect ok: true
/usr/bin/python3 scripts/aeo.py validate examples/demo                                          # Python 3.9 still works
python3 dev/smoke.py && /usr/bin/python3 dev/smoke.py                                          # setup + promo checks
(cd dev && npm i && npm run validate-blocks)                                                  # expect invalid: 0, first block core/embed
grep -rniIf private/brand-terms.txt --exclude-dir={.git,private,node_modules} --exclude=package-lock.json .   # expect no output
```
Iterate in Claude Code: `claude --plugin-dir .`

## Test in Claude Desktop
1. Bump `version` in `.claude-plugin/plugin.json` (Desktop may keep a stale copy of the same version).
2. `dev/package.sh` → `dist/video2aeo-<version>.plugin` (until the GitHub marketplace is set up).
3. Desktop → Settings → Plugins: remove the old plugin, upload the new file (or push and click Update).
4. New **Cowork** task with a working folder → `/video2aeo:episode` + transcript `.txt` (plain chat loads skills only).

The desktop app runs `.mcp.json`'s `python3` with the GUI PATH (`/usr/bin/python3`, 3.9 here), not Homebrew's (3.14).

## Status (12 Oct 2026)
v0.1 moved from a cloud session to the local Mac and made brand-neutral (plugin named `yt-aeo`). 0.4.0 renamed it to **Video2AEO** (`video2aeo`, settings `~/.video2aeo/`); the code still reads
the legacy `~/.yt-aeo/` folder and `YT_AEO_HOME` when the new ones are missing.
Demo render/validate ok on Python 3.14 and 3.9; 65 Gutenberg blocks, 0 invalid. **Not yet tested:** agents + MCP in
Desktop Cowork, live `fetch_transcript`, `wp_push_draft`.

## Next steps (full list: `docs/plugin-build-plan.md` §3)
1. Publish on GitHub + marketplace; install in Desktop from it.
2. Phase 1a manual MVP: first brand folder in `~/.video2aeo/`; transcript `.txt` → text files, end to end in Code and Desktop; 5 back-catalogue episodes; freeze `episode.json` v1.0.
3. `claude plugin eval` suite in `evals/` (excluded from the package).
4. Phase 1b: automatic subtitles, credential hardening, human-run gate sign-off, HTML allowlist, then WP draft push.
5. Phase 2: WordPress plugin „Video2AEO for WordPress“ (see plan).
