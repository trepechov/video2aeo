# yt-aeo – YouTube AEO Episode Agent

A Claude plugin that turns a podcast/video episode transcript into an AEO package. Add the transcript `.txt` of a new
episode and get, in one folder:

| Output | What it is |
|---|---|
| `transcript.raw.txt` | The transcript, grouped in timestamped paragraphs |
| `transcript.edited.md` | Edited, speaker-labelled, citable transcript (sponsor reads tagged) |
| `episode.json` | The knowledge map – single source of truth for everything below |
| `youtube-description.txt` | AEO description: direct answer → questions → article link → chapters → footer |
| `article.wp.html` | WordPress Gutenberg article: **video embed first**, answer block, takeaways, chapter links, question-H2 sections, tables, FAQ, transcript, authors, disclaimer, JSON-LD |
| `schema.jsonld` | Article + VideoObject (with chapter Clips) + FAQPage + Organization |
| `wp-post-fields.json` | Title (= video title), slug, SEO title, meta description, keyphrase, category, tags |
| `review.md` | Errors, warnings, placeholders, fact-check table, gate sign-offs |

You paste the description into YouTube Studio and the article into the WordPress Code editor. Automatic subtitle
download and WordPress draft push exist but are optional (see `docs/plugin-build-plan.md` §3.3).

## Who does what

- **Claude writes all text** (transcript edit, questions, chapters, description, article, FAQ), guided by the skills and agents.
- **Scripts do the mechanical parts** – import transcripts, assemble formats, enforce limits. The marketer never runs them by hand.
- **People approve** at three gates: A (facts, names, chapters, title), B (copy & SEO), C (compliance & publish go).

## Components

| Type | Name | Purpose |
|---|---|---|
| Skill | `aeo-episode` | Orchestrator: `/yt-aeo:aeo-episode` |
| Skill | `yt-description` | Description, chapters and title rules |
| Skill | `wp-article` | Article structure, block order, SEO fields |
| Skill | `setup` | One-time setup on the marketer's computer |
| Agent | `transcript-editor` | Raw transcript → edited transcript |
| Agent | `knowledge-mapper` | Edited transcript → `episode.json` |
| Agent | `aeo-reviewer` | Independent pre-Gate-B review |
| MCP (local) | `yt-aeo-tools` | `setup_status`, `check_environment`, `save_setup`, `import_transcript`, `render_package`, `validate_package`; optional `get_video_info`, `fetch_transcript`, `wp_push_draft` |

Agents and the local tool server load in **Cowork tasks running on the computer** (Claude desktop app) and in Claude
Code. In plain chat only the skills load: the user pastes the transcript and the agent follows the same steps.

## Brand, glossary and guidelines

The plugin is brand-neutral and ships general AEO guidelines and best practices
(`skills/aeo-episode/references/aeo-rules.md`). Each user's brand lives on their computer in `~/.yt-aeo/`:

| File | Purpose |
|---|---|
| `brand.json` | Channel, series, topics, site, organization, people, approved footer/promo block, disclaimer – any keys of `config/brand.json`, merged over it |
| `glossary.json` | Brand names, people, ASR fixes, sponsor-read markers – added to `config/glossary.json` |
| `guidelines.md` or `guidelines/*.md` | Brand-specific instructions (house style, tone, terminology, compliance); they extend the general guidelines |
| `config.json` | Optional WordPress credentials for the draft push (`chmod 600`) |

You normally never edit these files: the `setup` skill writes them after you approve a summary (the previous
`guidelines.md` is kept as `guidelines.md.bak`; a damaged file is kept as `<name>.broken` and rewritten). Channel name
and topics are required; skipped optional values are saved empty. Set `YT_AEO_HOME` to use another folder.

## Setup

1. Install the plugin from GitHub – everything is done with the mouse:
   - Claude desktop app (Mac): Claude menu → **Settings** → **Plugins** → **Add** (top right) → add marketplace →
     enter the GitHub repository `trepechov/yt-aeo-helper` → search for **YouTube AEO Episode Agent** → **Install**
     → make sure it is switched on (not "Disabled").
   - Claude Code: `/plugin install yt-aeo --marketplace trepechov/yt-aeo-helper`
     (or `claude plugin marketplace add trepechov/yt-aeo-helper && claude plugin install yt-aeo@yt-aeo-helper`).
   Then open a **new** Cowork task: `/yt-aeo:` commands appear when you type `/`.
2. Python 3.9+ on the computer (preinstalled on macOS).
3. First use: just run any `/yt-aeo:` command in a Cowork task. If the one-time setup is not done, the `setup` skill
   starts by itself and asks for the channel, the promo block (links, messages, ads) and whether it goes at the top or
   the end of the description, and shows the AEO guidelines to follow or switch off. It writes `~/.yt-aeo/` for you –
   no files to edit by hand. Re-run `/yt-aeo:setup` any time to change the answers.
4. Optional, needs a terminal: subtitle download – install into the interpreter the desktop app uses (on macOS usually `/usr/bin/python3`,
   not Homebrew's): `/usr/bin/python3 -m pip install --user youtube-transcript-api`.

## Updating

When a new version is published (the `version` in the repository changes), open Settings → Plugins, refresh the
marketplace if the new version is not shown, and click **Update** on **yt-aeo**. Start a new Cowork task afterwards.
Your brand settings in `~/.yt-aeo/` are not touched.

## Usage

In a Cowork task with a working folder: run `/yt-aeo:aeo-episode` and add or attach the transcript `.txt`.

## Developing (Claude Code) and testing (Claude Desktop)

The repo root is the plugin. Develop in Claude Code, which loads skills, agents and the MCP server:

```bash
claude --plugin-dir .                              # load locally
claude plugin validate .                           # manifest/structure
export YT_AEO_HOME=examples/demo                   # fictional demo brand
python3 scripts/aeo.py render examples/demo && python3 scripts/aeo.py validate examples/demo
python3 dev/smoke.py                               # setup flow + promo/footer rendering (temp settings folder)
cd dev && npm i && npm run validate-blocks         # WordPress's own block validator on the rendered article
```

Test the installed plugin in the Claude desktop app:

1. Bump `version` in `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` – `dev/release.sh <version>`
   does both and runs the checks.
2. `dev/package.sh` → `dist/yt-aeo-<version>.plugin`.
3. Settings → Plugins: remove the old version, upload the new file (or push to GitHub and use **Update**).
4. Open a Cowork task with a working folder and run `/yt-aeo:aeo-episode`.

### Releasing a new version

No build or publish script is required – the marketplace reads the GitHub repository directly. The only rule: Claude
detects an update by comparing the `version` field, so it must change.

```bash
dev/release.sh 0.2.1                     # runs all checks, then bumps manifests + skill versions
git add -A && git commit -m "yt-aeo 0.2.1" && git push
```

Users then see the new version under Settings → Plugins and click **Update**.

`examples/demo/` is the golden example (fictional brand and episode): any renderer change must keep it valid with 0
invalid blocks. Real brand files belong in the git-ignored `private/` folder, never in commits.
See `docs/plugin-build-plan.md` for the roadmap.
