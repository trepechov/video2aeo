# Video2AEO

```text
  ┌──────────────────────┐              ┌────────────────────────────┐
  │                      │              │ Q  How do I start a show?  │
  │          ▶           │              │ A  Pick one topic, one mic │
  │                      │   ────────▶  │    and a weekly slot.      │
  │ ▁▂▃▅▇▅▃▂▁▂▃▅▇▅▃▂▁▂▃▅ │   video2aeo  │ 00:00  Chapters            │
  │ ●━━━━━━━━━──── 12:04 │              │ </>    Article + FAQ       │
  └──────────────────────┘              └────────────────────────────┘
       one episode in                      answers AI can quote
```

**One video in, AEO content out.** Video2AEO (plugin ID `video2aeo`) takes a YouTube episode and produces
answer-ready content – the YouTube description first, then the WordPress article that covers all questions and
answers. Written for human readers, found by Google and AI answers.

A Claude plugin that turns a podcast/video episode transcript into an AEO package, one command per output:

| Command | Produces | When |
|---|---|---|
| `/video2aeo:episode <url>` | The knowledge map and the **YouTube description** with chapters and title | Main command – run first |
| `/video2aeo:wp-article` | The **WordPress (Gutenberg) article** with the video embedded first, FAQ, schema and SEO fields | After `episode`, when the article is wanted |

More outputs (social posts, newsletter …) will follow the same pattern: one instruction file, one command.

Each episode gets one folder. What you paste is in the folder itself; everything else is in `work/`:

```
episodes/<yyyy-mm>-<series>-<nn>-<slug>/        e.g. episodes/2026-01-show-12-episode-slug/
├── youtube-description.txt     AEO description: direct answer → questions → article link → chapters → footer
├── article.wp.html             Gutenberg article: video embed first, answer, takeaways, chapters, FAQ, transcript, JSON-LD
├── wp-post-fields.json         Title (= video title), slug, SEO title, meta description, keyphrase, category, tags
└── work/                       working files – not meant to be read
    ├── episode.json            the knowledge map – single source of truth for every output
    ├── transcript.raw.txt / .json, transcript.edited.md
    └── schema.jsonld, review.md (errors, warnings, fact-check, approvals), wp-result.json
```

You paste the description into YouTube Studio and the article into the WordPress Code editor. Automatic subtitle
download and WordPress draft push exist but are optional (see `docs/plugin-build-plan.md` §3.3).

## Who does what

- **Claude writes all text** (transcript edit, questions, chapters, description, article, FAQ), guided by the
  instruction files in `instructions/` (one per output) and the agents.
- **Scripts do the mechanical parts** – import transcripts, assemble formats, enforce limits. The marketer never runs them by hand.
- **People approve**: Gate A (facts, names, chapters, title) in `episode`, then one approval per output
  (description, article).

## Instructions

`instructions/` holds the plugin's general instructions – `aeo-rules.md` (principles), `youtube-description.md`,
`wordpress-article.md` (structure, SEO fields, tags, internal links), and `episode-schema.md`.
Brand additions go to `~/.video2aeo/guidelines/<same file name>`. See `instructions/README.md`.

## Components

| Type | Name | Purpose |
|---|---|---|
| Skill | `episode` | `/video2aeo:episode` – transcript → knowledge map → YouTube description |
| Skill | `wp-article` | `/video2aeo:wp-article` – article for an episode |
| Skill | `setup` | One-time setup on the marketer's computer |
| Agent | `transcript-editor` | Raw transcript → edited transcript |
| Agent | `knowledge-mapper` | Edited transcript → `episode.json` |
| Agent | `aeo-reviewer` | Independent review before each approval |
| MCP (local) | `video2aeo` | `setup_status`, `check_environment`, `save_setup`, `import_transcript`, `render_package`, `validate_package`; optional `get_video_info`, `fetch_transcript`, `wp_push_draft` |

Agents and the local tool server load in **Cowork tasks running on the computer** (Claude desktop app) and in Claude
Code. In plain chat only the skills load: the user pastes the transcript and the agent follows the same steps.

## Brand, glossary and guidelines

The plugin is brand-neutral and ships general AEO guidelines and best practices
(`instructions/aeo-rules.md`). Each user's brand lives on their computer in `~/.video2aeo/`:

| File | Purpose |
|---|---|
| `brand.json` | Channel, series, topics, site, organization, people, approved footer/promo block, disclaimer – any keys of `config/brand.json`, merged over it |
| `glossary.json` | Brand names, people, ASR fixes, sponsor-read markers – added to `config/glossary.json` |
| `guidelines.md` or `guidelines/*.md` | Brand-specific instructions (house style, tone, terminology, compliance); they extend the general guidelines |
| `config.json` | Optional: WordPress credentials for the draft push, and `youtube.cookies_from_browser` / `youtube.cookies_file` for the subtitle download (`chmod 600`) |

You normally never edit these files: the `setup` skill writes them after you approve a summary (the previous
`guidelines.md` is kept as `guidelines.md.bak`; a damaged file is kept as `<name>.broken` and rewritten). Channel name
and topics are required; skipped optional values are saved empty. Set `VIDEO2AEO_HOME` to use another folder.

## Setup

1. Install the plugin from GitHub – everything is done with the mouse:
   - Claude desktop app (Mac): Claude menu → **Settings** → **Plugins** → **Add** (top right) → add marketplace →
     enter the GitHub repository `trepechov/video2aeo` → search for **Video2AEO** → **Install**
     → make sure it is switched on (not "Disabled").
   - Claude Code: `/plugin install video2aeo --marketplace trepechov/video2aeo`
     (or `claude plugin marketplace add trepechov/video2aeo && claude plugin install video2aeo@video2aeo`).
   Then open a **new** Cowork task: `/video2aeo:` commands appear when you type `/`.
2. Python 3.9+ on the computer (preinstalled on macOS).
3. First use: just run any `/video2aeo:` command in a Cowork task. If the one-time setup is not done, the `setup` skill
   starts by itself and asks for the channel, the description header and footer (links, messages, ads), the brand
   glossary (names, caption mistakes), and shows the AEO guidelines for you to verify, follow or switch off. It writes `~/.video2aeo/` for you –
   no files to edit by hand. Re-run `/video2aeo:setup` any time to change the answers.

### Automatic subtitle download (optional, one-time, ~2 minutes)

Without it you attach the transcript `.txt` (YouTube Studio → Subtitles → download) – that always works. To let the
plugin fetch the subtitles from the video address, install one downloader. No YouTube API key and no channel access
are needed for public videos.

1. **Recommended – `yt-dlp`** (a standalone program, no Python version to worry about):
   ```bash
   brew install yt-dlp
   ```
   Alternative, a Python package: `python3 -m pip install --user youtube-transcript-api` – use the same `python3`
   the plugin runs with (in the Claude desktop app on macOS this is `/usr/bin/python3`, not Homebrew's).
2. Restart the Claude app (or start a new Claude Code session) so it sees the new program.
3. Only if YouTube answers „Sign in to confirm you're not a bot“ or blocks your address: let `yt-dlp` use a logged-in
   browser. Any YouTube account works, it does not have to be the channel's (a separate account is safer – automated
   use can get an account flagged). Create `~/.video2aeo/config.json` (`chmod 600`):
   ```json
   { "youtube": { "cookies_from_browser": "chrome" } }
   ```
   or, if the browser's keychain is not reachable from the app, export a `cookies.txt` once and use
   `{ "youtube": { "cookies_file": "~/.video2aeo/cookies.txt" } }`. Cookies are a password: never paste them into chat
   or commit them. Private or unpublished videos still need an account that has access to them.

### Minimal setup on a marketer's computer

1. Install Claude (desktop app or Claude Code) and sign in.
2. Add the marketplace and install the plugin (step 1 above).
3. Run `/video2aeo:setup` once and answer the questions (channel, header/footer, glossary, guidelines).
4. Optional: `brew install yt-dlp` for automatic subtitles. Python is preinstalled on macOS.

That is all – then `/video2aeo:episode` with the episode address or transcript.

## Updating

When a new version is published (the `version` in the repository changes), open Settings → Plugins, refresh the
marketplace if the new version is not shown, and click **Update** on **video2aeo**. Start a new Cowork task afterwards.
Your brand settings in `~/.video2aeo/` are not touched. Settings of the former name (`yt-aeo`) in `~/.yt-aeo/` are
still read if `~/.video2aeo/` does not exist.

## Usage

In a Cowork task with a working folder: run `/video2aeo:episode` with the video address, or attach the transcript `.txt`; then `/video2aeo:wp-article` for the article.

## Developing (Claude Code) and testing (Claude Desktop)

The repo root is the plugin. Develop in Claude Code, which loads skills, agents and the MCP server:

```bash
claude --plugin-dir .                              # load locally
claude plugin validate .                           # manifest/structure
python3 dev/smoke.py                               # setup flow, rendering and validation on a built-in fictional episode (temp folders)
cd dev && npm i && npm run validate-blocks         # WordPress's own block validator on that rendered article
```

Test the installed plugin in the Claude desktop app:

1. Bump `version` in `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` – `dev/release.sh <version>`
   does both and runs the checks.
2. `dev/package.sh` → `dist/video2aeo-<version>.plugin`.
3. Settings → Plugins: remove the old version, upload the new file (or push to GitHub and use **Update**).
4. Open a Cowork task with a working folder and run `/video2aeo:episode`.

### Releasing a new version

No build or publish script is required – the marketplace reads the GitHub repository directly. The only rule: Claude
detects an update by comparing the `version` field, so it must change.

```bash
dev/release.sh 0.3.1                     # runs all checks, then bumps manifests + skill versions
git add -A && git commit -m "video2aeo 0.3.1" && git push
```

Users then see the new version under Settings → Plugins and click **Update**.

The checks build a fictional episode on the fly (`dev/fixture.py`); no example folder is kept in the repository. Any
renderer change must keep it valid with 0 invalid blocks. Real brand files belong in the git-ignored `private/` folder, never in commits.
See `docs/plugin-build-plan.md` for the roadmap.
