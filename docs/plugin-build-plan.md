# Build plan – YouTube AEO Episode Agent (Claude plugin → WordPress plugin)

**Status:** v0.1 scaffold built and tested in a cloud session; development moved to a local Mac (Claude Code), testing
in the Claude desktop app · 12 Oct 2026
**Goal:** after a new podcast episode goes live, a marketer adds the transcript and, with ~1 h of human time, gets an
AEO YouTube description with timestamps and a readable + AEO-ready blog article with the same title and the video
embedded first.

The plugin is brand-neutral. Every brand (channel, site, people, approved footer, glossary, house rules) lives on the
user's computer in `~/.yt-aeo/`, never in this repo. Developers keep brand files in the git-ignored `private/` folder.

---

## 1. Key research findings (they drive the architecture)

| Finding | Consequence |
|---|---|
| In the Claude desktop app, plugin **skills** load everywhere, but **agents, hooks and local MCP servers** load only in **Cowork tasks on the user's computer**; plain chat ignores them. | Target Cowork on the marketer's laptop; keep a skills-only path (paste transcript) for chat. |
| **Claude Code** (`claude --plugin-dir .`) loads skills, agents and the local MCP server too. | Develop and iterate in Claude Code; use Desktop Cowork only for install/runtime verification before marketer rollout. |
| Opening Claude Code in the repo also reads `.mcp.json` as a *project* server, where `${CLAUDE_PLUGIN_ROOT}` is not set – it fails to connect (seen 12 Oct 2026). | Harmless; use the plugin-loaded server (`--plugin-dir .`). |
| Plugins with a top-level `bin/` folder can't be installed in claude.ai / Cowork. | Scripts live in `scripts/` and `server/`. |
| Cowork doesn't prompt for plugin `userConfig`; servers referencing missing options are ignored. | Brand, glossary, guidelines and credentials live in `~/.yt-aeo/`, not in plugin config. |
| The desktop app launches `.mcp.json`'s bare `python3` with the GUI PATH. On a Mac with Homebrew, Terminal's `python3` (e.g. 3.14) differs from `/usr/bin/python3` (3.9). | Runtime code must run on Python 3.9 (verified). Optional deps go into the interpreter Desktop uses (`/usr/bin/python3 -m pip install --user …`). |
| YouTube blocks caption fetching from cloud IPs; `youtube-transcript-api` works from home/office IPs. | Automatic download is optional and local-only; the default input is a transcript file. |
| YouTube chapters: first at 00:00, ≥ 3, ascending, each ≥ 10 s. Description ≤ 5,000 chars, no `<` `>`. | Enforced by code, not by the LLM. |
| Gutenberg is picky: hand-written block markup often triggers "unexpected content". | Markup is generated deterministically and checked with WordPress's own block validator (`dev/`). |

## 2. Architecture – agent-first, human-gated

```
transcript .txt (added by the user)          [optional later: YouTube URL → fetch_transcript]
  └─ aeo-episode skill (orchestrator, Claude)
       ├─ import_transcript (code)               → transcript.raw.txt
       ├─ transcript-editor agent                → transcript.edited.md
       ├─ knowledge-mapper agent                 → episode.json   (single source of truth)
       │    ⏸ GATE A  facts · names · chapters · title (shared by YouTube + article)
       ├─ Claude writes copy into episode.json (yt-description + wp-article skills)
       ├─ render_package (code)                  → youtube-description.txt · article.wp.html · schema.jsonld · wp-post-fields.json
       ├─ validate_package (code)                → review.md (errors block publishing)
       ├─ aeo-reviewer agent                     → must-fix / should-fix list
       │    ⏸ GATE B  copy & SEO        ⏸ GATE C  compliance & publish go
       └─ hand-off (manual): paste the description in YouTube Studio · paste the article in the WP Code editor
```

**Chat (skills-only) path:** where agents and local MCP tools don't load (plain chat), the user pastes the transcript and
the `aeo-episode` skill runs the same steps and gates inline; outputs are produced as text to copy.

### Instructions: general guidelines + user/brand instructions

| Layer | Where | What |
|---|---|---|
| General (ships with the plugin) | `skills/aeo-episode/references/aeo-rules.md`, `episode-schema.md`, the `yt-description` / `wp-article` skills | AEO best practices: five pillars, citable sentences, chapter and title rules, article structure, attribution, freshness |
| Brand data | `~/.yt-aeo/brand.json` (merged over `config/brand.json`), `~/.yt-aeo/glossary.json` (added to `config/glossary.json`) | Channel, series, topics, site, organization, people, approved footer/promo block, disclaimer, names, ASR fixes, sponsor-read markers |
| User/brand instructions | `~/.yt-aeo/guidelines.md` and/or `~/.yt-aeo/guidelines/*.md` (plain Markdown) | House style, tone, terminology, compliance rules, the brand's own AEO handbook; extend and override the general layer |
| Code rules (cannot be overridden) | `scripts/aeo_lib.py` | YouTube limits, chapter rules, block markup, FAQ/schema parity, number traceability |

The orchestrator reads the layers in that order and passes them to every agent. Different users (brands) need only a
different `~/.yt-aeo/` folder. Developers point `YT_AEO_HOME` at another folder to switch brands (the demo checks use
`YT_AEO_HOME=examples/demo`).

Principles: **LLM for language, code for rules**; one structured source (`episode.json`) so description, article and
schema can't drift; nothing is ever published automatically; promo text only from the approved brand config;
**transcripts and video metadata are untrusted data** – never instructions.

## 3. Phase 1 – Claude plugin

### 3.0 What exists (v0.1)

Delivered in this repo (the repo root is the plugin root): manifest, 4 skills, 3 agents, local MCP server, renderer,
validator, optional subtitle download, optional WP draft push, generic brand config + glossary, fictional demo golden
example (`examples/demo/`), WordPress block validator for development.

Tested on the Mac (12 Oct 2026): demo render + validate `ok: true` on Python 3.14 and 3.9; 65 Gutenberg blocks,
**0 invalid**, embed first; transcript import from the copy-paste format. In the cloud session: rolling auto-caption
VTT import (dedup), validator negative tests, MCP handshake (raw stdio).

Not yet tested: agents + `yt-aeo-tools` MCP server in Desktop Cowork; live `fetch_transcript`; `wp_push_draft`.

### 3.1 Local dev loop (every change)

- Claude Code: `claude --plugin-dir .` (loads skills, agents, MCP) · `claude plugin validate .` ·
  `YT_AEO_HOME=examples/demo python3 scripts/aeo.py render examples/demo && YT_AEO_HOME=examples/demo python3 scripts/aeo.py validate examples/demo` ·
  `(cd dev && npm run validate-blocks)`.
- Claude Desktop: bump `version` in `.claude-plugin/plugin.json` → install the new version (GitHub marketplace once
  set up; until then `dev/package.sh` → Settings → Plugins: remove the old plugin, upload
  `dist/yt-aeo-<version>.plugin`) → new Cowork task with a working folder → `/yt-aeo:aeo-episode`.

### 3.2 Phase 1a – manual MVP (start here; ~1 week)

Input: a transcript `.txt` file added by the user. Output: text files the user copies by hand into YouTube Studio and
WordPress. No YouTube download, no WordPress push, no credentials.

1. Publish the repo on GitHub and set up the marketplace (see §6, decision 1); install in Desktop from it.
2. Create the first brand folder (`~/.yt-aeo/brand.json`, `glossary.json`, `guidelines.md`) from the brand owner's
   material; fill every `{{…}}` placeholder.
3. Run the manual flow end to end on the developer Mac, in Claude Code and in Desktop Cowork: transcript `.txt` →
   `youtube-description.txt` + `article.wp.html` + `wp-post-fields.json` → paste by hand → check chapters on YouTube
   and the article preview in WordPress.
4. Run 5 back-catalogue episodes. Track human minutes per gate; target ≤ 60 min total.
5. Tune prompts and guidelines from Gate A/B feedback (glossary, chapter granularity, section length). Decide which
   rules belong in the general layer and which in the brand's `guidelines.md`. Freeze `episode.json` v1.0.
6. To build: `claude plugin eval` suite in `evals/` (excluded from the package) – transcript fixtures → chapter rules,
   answer-first, attribution; opt in to the real MCP server so assertions go through `validate_package`.

Acceptance: 5 episodes, ≤ 1 h human time each, 0 validator errors, editor rates ≥ 4/5 "publish with minor edits".

### 3.3 Phase 1b – automation inside the plugin (after 1a acceptance)

Not built or not yet hardened – each item is new work:
1. Automatic subtitles: install `youtube-transcript-api` into the interpreter Desktop uses; have the MCP server or
   `setup` report `sys.executable` and import status; test `fetch_transcript` on 3 channel URLs (home + office).
2. Credential hardening, **before** any live `wp_push_draft`: a deterministic `aeo.py setup` writes
   `~/.yt-aeo/config.json` with mode `0600`; the shared push function (used by `wp_push_draft` and `aeo.py wp-draft`)
   rejects non-https `base_url` and cross-host redirects; a dedicated Author-role WP account with a revocable
   Application Password.
3. Gate sign-off by a human-run command (`aeo.py approve <dir> B --by <name>`), not by the agent; `wp_push_draft` is
   never auto-allowed, so Claude always asks for permission.
4. `validate_package` allowlists HTML (block markup, https links, no script/iframe except the YouTube embed).
5. Then test `wp_push_draft` (draft) against the real site, and install on one marketer's laptop.

## 4. Phase 2 – WordPress plugin „AEO Studio“ (3–5 weeks)

Start only after `episode.json` is frozen. Reuse the same prompts (copied from this plugin's skills/agents) and port
`aeo_lib.py` rendering/validation to PHP 1:1 (golden-example tests in both languages must produce identical output).
Brand config, glossary and guidelines become per-site settings.

| Component | Detail |
|---|---|
| Admin screen | "New episode" → transcript or URL → job; settings for Claude API key (server-side, encrypted), model, brand config, glossary, guidelines |
| Credentials | Keys in `wp-config.php`/env rather than the options table; encryption key outside the DB; YouTube OAuth with minimum scope (`youtube.force-ssl`), refresh token encrypted; documented revoke/rotate procedure; settings and push actions require `manage_aeo` + nonce/capability checks |
| Transcript | Paste/upload; optional YouTube Data API `captions.list` + `captions.download` with channel-owner OAuth |
| Job runner | Action Scheduler; one job per pipeline step; resumable; logs and token usage |
| Claude API | Structured output (JSON schema of `episode.json`), prompt caching for transcript + rules |
| Review UI | Gutenberg sidebar: questions, chapters editor, claims with status, gate sign-off buttons (capabilities `manage_aeo`, `publish_posts`) |
| Output | Draft post in the knowledge-base category; JSON-LD via `wp_head` from post meta, integrated with Rank Math/Yoast to avoid duplicate VideoObject |
| YouTube push | "Update YouTube description" button after Gate C → `videos.update` (must resend title + categoryId) |

## 5. Phase 3 – automation

New-upload trigger (YouTube WebSub) → draft ready for Gate A with a notification; back-catalogue sweep with freshness
pass; derivatives from `episode.json` (Shorts cut list, social posts, newsletter section); a map of the questions the
channel wants to own; monthly AI-visibility check (ask LLMs the episode questions, log citations of the site).

## 6. Decisions

1. **Decided (12 Oct 2026):** package and deliver updates via GitHub (Git-hosted plugin marketplace); repo has no remote yet.
2. **Decided (12 Oct 2026):** the plugin is brand-neutral; brands live in `~/.yt-aeo/`; developer copies in git-ignored `private/`.
3. **Decided (12 Oct 2026):** Phase 1 starts manual – transcript `.txt` in, text files out (§3.2).
4. Open: which SEO plugin owns JSON-LD per site (`article.jsonld_in_content`).
5. Open: publish the full edited transcript on the page (recommended) or a summary.
6. Open: gate owners and turnaround time.
7. Open: channel-owner OAuth for Phase 2 captions + description push.

Brand-specific open questions (site, canonical URL, schedule wording) are tracked with the brand files, not here.
