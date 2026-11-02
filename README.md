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

## Requirements

| | Windows | macOS |
|---|---|---|
| **Claude** | Claude desktop app (or Claude Code CLI) | same |
| **Python 3.9 or newer** | python.org/downloads – on the first screen of the installer **tick „Add python.exe to PATH“** (or install Python from the Microsoft Store) | python.org/downloads („macOS 64-bit universal2 installer“), or `xcode-select --install` in Terminal |
| **Git for Windows** | git-scm.com, default options | not needed |

Restart the Claude app after installing either one. If anything is missing later, `/video2aeo:doctor` checks the
computer and walks you through the fix (on Windows it also adds Git's folder to your PATH, with your OK).

## Install

1. **Add the plugin.** Claude desktop app: Settings → **Plugins** → **Add** → add marketplace `trepechov/video2aeo` →
   **Video2AEO** → **Install** (make sure it is switched on). Claude Code CLI:
   `/plugin install video2aeo --marketplace trepechov/video2aeo`.
2. **Switch to Claude Code mode** (toggle at the top left of the app), create a **new environment** and choose the
   folder you work in (your episodes folder). `/video2aeo:` commands appear when you type `/`.
3. **Run any `/video2aeo:` command.** The first time, setup starts by itself.

## First run: two ways to set up

- **Answer the questions** – channel, description header and footer (links, ads), brand glossary (names, caption
  mistakes), episode formats, and the AEO guidelines to follow or switch off. Best for the first person in a team.
- **Import a colleague's setup** – a colleague who already uses the plugin says „share my setup“ and sends you the
  `video2aeo-setup-<channel>-<date>.zip`. You choose „import a colleague's setup“, review what it brings (its guidelines
  and published texts are shown in full), and answer only what belongs to your computer – the episodes folder.

Either way setup ends by offering the automatic subtitle download, and writes `~/.video2aeo/` for you – no files to
edit by hand. Re-run `/video2aeo:setup` any time to change answers, import again or share.

**Share your setup:** say „share my setup“ (or run `/video2aeo:setup` and ask). You get one `.zip` with the brand,
glossary, guidelines, episode formats, switched-off guidelines and model choices – never WordPress passwords, YouTube
cookies or your episodes folder. It is private brand material: send it to colleagues only. Importing replaces the
team settings on the other computer and keeps the previous ones in a `backup-<date>` folder.

## Usage

In Claude Code mode with a working folder: run `/video2aeo:episode` with the video address, or attach the transcript
`.txt`; then `/video2aeo:wp-article` for the article. After a crash, `/video2aeo:resume` continues where it stopped.

### Automatic subtitle download (optional)

Without it you attach the transcript `.txt` (YouTube Studio → Subtitles → download) – that always works. With it the
plugin fetches the subtitles from the video address using two small Python packages, `youtube-transcript-api` and
`yt-dlp` (no YouTube API key, no channel access for public videos). Setup offers to install them at its end, and
`/video2aeo:episode` offers it again only when it needs them; they go into the Python the plugin runs on (no admin
rights, no restart). If that fails, the offer shows the exact command to run by hand; on a Homebrew/Linux Python it
suggests `brew install yt-dlp` or `pipx install yt-dlp`.

If YouTube answers „Sign in to confirm you're not a bot“ or blocks your address, let `yt-dlp` use a logged-in browser.
Any YouTube account works, it does not have to be the channel's (a separate account is safer – automated use can get
an account flagged). Create `~/.video2aeo/config.json` (`chmod 600`):
```json
{ "youtube": { "cookies_from_browser": "chrome" } }
```
or, if the browser's keychain is not reachable from the app, export a `cookies.txt` once and use
`{ "youtube": { "cookies_file": "~/.video2aeo/cookies.txt" } }`. Cookies are a password: never paste them into chat
or commit them. Private or unpublished videos still need an account that has access to them.

## Updating

When a new version is published (the `version` in the repository changes), open Settings → Plugins, refresh the
marketplace if the new version is not shown, and click **Update** on **video2aeo**. Start a new Claude Code environment
afterwards. Your settings in `~/.video2aeo/` are not touched.

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
| Skill | `resume` | `/video2aeo:resume` – continue an episode that crashed or stopped half way, from the files on disk |
| Skill | `setup` | `/video2aeo:setup` – interview or import a colleague's setup; share your own |
| Skill | `doctor` | `/video2aeo:doctor` – why the tools do not start; works without the plugin's helper |
| Agent | `transcript-editor` | Raw transcript → edited transcript |
| Agent | `knowledge-mapper` | Edited transcript → `episode.json` |
| Agent | `aeo-reviewer` | Independent review before each approval |
| Hook | SessionStart | Python-free check that Python (and on Windows `sh`) can be found; never blocks |
| MCP (local) | `video2aeo` | `setup_status`, `check_environment`, `save_setup`, `read_setup_bundle`, `export_setup`, `workspace_status`, `episode_path`, `episode_status`, `split_transcript`, `merge_transcript`, `progress_note`, `import_transcript`, `render_package`, `validate_package`; optional `install_subtitle_tools`, `get_video_info`, `fetch_transcript`, `wp_push_draft` |

Agents, the hook and the local tool server load in **Claude Code mode** of the desktop app and in the Claude Code CLI.
In plain chat only the skills load, so always work in Code mode.

**Long episodes and crashes.** The transcript is edited in chunks (`work/chunks/`), each finished chunk is a file, and
`episode_status` works out where an episode stands from the files – so after a crash `/video2aeo:resume` continues with
only what is left. **Models:** heavy, mechanical steps run on suitable models by themselves (defaults in
`config/models.json`), whatever model is selected in the app. To change that, ask the `setup` skill to „change the
models“ (profile fast / balanced / quality, or single operations).

## Brand, glossary and guidelines

The plugin is brand-neutral and ships general AEO guidelines and best practices (`instructions/aeo-rules.md`). Each
user's brand lives on their computer in `~/.video2aeo/`:

| File | Purpose |
|---|---|
| `brand.json` | Channel, series, topics, site, organization, people, episode formats, approved footer/promo block, disclaimer – any keys of `config/brand.json`, merged over it |
| `glossary.json` | Brand names, people, ASR fixes, sponsor-read markers – added to `config/glossary.json` |
| `guidelines.md` and `guidelines/*.md` | Brand-specific instructions (house style, tone, terminology, compliance); they extend the general guidelines, `guidelines/<output>.md` per output |
| `setup.json` | Setup done, guidelines switched off |
| `config.json` | This computer only: episodes folder, model choices, and optionally WordPress credentials and YouTube cookies (`chmod 600`) – never shared |

You normally never edit these files: the `setup` skill writes them after you approve a summary (the previous
`guidelines.md` is kept as `guidelines.md.bak`, an import keeps the replaced files in `backup-<date>/`, a damaged file
is kept as `<name>.broken`). Set `VIDEO2AEO_HOME` to use another folder.

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
4. Switch to Claude Code mode, create a new environment with a working folder and run `/video2aeo:episode`.

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
