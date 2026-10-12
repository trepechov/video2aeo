# yt-aeo-helper – project memory for Claude Code

This repo is the **yt-aeo** Claude plugin ("YouTube AEO Episode Agent"). Given the transcript of a new podcast/video
episode it produces an edited transcript, an AEO YouTube description with chapters, and a WordPress (Gutenberg)
article with the same title as the video and the video embedded as the first block – as text files the user pastes
by hand. Semi-automated: the agent drafts, humans approve at Gates A/B/C.

Content language is **Bulgarian**; code, comments and docs are English.

## Brand-neutral repo (do not break)
- No real brand data in commits: no channel/company names, people, site URLs, promo text, brand glossary or real
  episodes. Brands live in `~/.yt-aeo/` on the user's computer (`brand.json`, `glossary.json`, `guidelines.md`,
  `config.json`); `config/` holds generic defaults with `{{PLACEHOLDERS}}`.
- Developer brand files and the pre-neutral snapshot live in git-ignored `private/` (see `private/BRAND-NOTES.md`).
  Read them for context; never copy their content into tracked files.
- Examples use the fictional demo brand in `examples/demo/`.

## Read first
- `docs/plugin-build-plan.md` – architecture, instruction layers, roadmap (phase 1a manual MVP → 1b automation → phase 2 WordPress plugin → phase 3), decisions.
- `skills/aeo-episode/references/aeo-rules.md` – the general AEO guidelines shipped with the plugin.
- `skills/aeo-episode/references/episode-schema.md` – `episode.json`, the single source of truth.

## Layout
- `.claude-plugin/plugin.json` – manifest (plugin name `yt-aeo`; commands are `/yt-aeo:<skill>`).
- `skills/` – `aeo-episode` (orchestrator), `yt-description`, `wp-article`, `setup`.
- `agents/` – `transcript-editor`, `knowledge-mapper`, `aeo-reviewer`. Frontmatter `description` must be a YAML block scalar (`|`).
- `.mcp.json` + `server/server.py` – local stdio MCP server `yt-aeo-tools` (stdlib-only Python).
- `scripts/aeo_lib.py` – parsing, rendering (description, Gutenberg, JSON-LD), validation, brand loading (`USER_DIR`,
  `YT_AEO_HOME`). `scripts/aeo_net.py` – optional YouTube + WordPress network calls. `scripts/aeo.py` – CLI.
- `config/brand.json`, `config/glossary.json` – generic defaults, merged with `~/.yt-aeo/` files.
- `examples/demo/` – golden example (fictional brand + episode). Must stay valid.
- `dev/` – developer-only: WordPress block validator, `package.sh`. Not shipped.

## Principles (do not break)
1. LLM writes language; code enforces rules (YouTube limits, chapter rules, block markup, schema, number traceability).
2. Every output is rendered from `episode.json` – never hand-edit rendered files.
3. Nothing publishes automatically. WordPress push is optional, draft-only and requires Gate B.
4. Promo text comes only from the approved brand config; opinions and forecasts are always attributed.
5. General guidelines ship with the plugin; brand/user instructions come from `~/.yt-aeo/guidelines*.md` and may
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
export YT_AEO_HOME=examples/demo
python3 scripts/aeo.py render examples/demo && python3 scripts/aeo.py validate examples/demo   # expect ok: true
/usr/bin/python3 scripts/aeo.py validate examples/demo                                          # Python 3.9 still works
(cd dev && npm i && npm run validate-blocks)                                                  # expect invalid: 0, first block core/embed
grep -rniIf private/brand-terms.txt --exclude-dir={.git,private,node_modules} --exclude=package-lock.json .   # expect no output
```
Iterate in Claude Code: `claude --plugin-dir .`

## Test in Claude Desktop
1. Bump `version` in `.claude-plugin/plugin.json` (Desktop may keep a stale copy of the same version).
2. `dev/package.sh` → `dist/yt-aeo-<version>.plugin` (until the GitHub marketplace is set up).
3. Desktop → Customize → Plugins: remove the old plugin, upload the new file.
4. New **Cowork** task with a working folder → `/yt-aeo:aeo-episode` + transcript `.txt` (plain chat loads skills only).

The desktop app runs `.mcp.json`'s `python3` with the GUI PATH (`/usr/bin/python3`, 3.9 here), not Homebrew's (3.14).

## Status (12 Oct 2026)
v0.1 moved from a cloud session to the local Mac and made brand-neutral (plugin renamed to `yt-aeo`).
Demo render/validate ok on Python 3.14 and 3.9; 65 Gutenberg blocks, 0 invalid. **Not yet tested:** agents + MCP in
Desktop Cowork, live `fetch_transcript`, `wp_push_draft`.

## Next steps (full list: `docs/plugin-build-plan.md` §3)
1. Publish on GitHub + marketplace; install in Desktop from it.
2. Phase 1a manual MVP: first brand folder in `~/.yt-aeo/`; transcript `.txt` → text files, end to end in Code and Desktop; 5 back-catalogue episodes; freeze `episode.json` v1.0.
3. `claude plugin eval` suite in `evals/` (excluded from the package).
4. Phase 1b: automatic subtitles, credential hardening, human-run gate sign-off, HTML allowlist, then WP draft push.
5. Phase 2: WordPress plugin „AEO Studio“ (see plan).
