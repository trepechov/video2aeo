---
name: aeo-episode
description: >
  This skill should be used when the user gives a YouTube URL of a new podcast/video
  episode and asks to "process the episode", "make the AEO package", "prepare the YouTube description and blog
  article", "download the subtitles and write the article", or runs /yt-aeo:aeo-episode <url>. It orchestrates the
  whole semi-automated workflow: subtitles → edited transcript → knowledge map (episode.json) → AEO YouTube
  description with chapters → WordPress Gutenberg article with the video embedded first → schema → checks,
  stopping at three human approval gates.
metadata:
  version: "0.2.0"
---

# AEO Episode Agent – orchestrator

Turn one YouTube URL into an approved AEO package. Write every piece of text yourself; use the
`yt-aeo-tools` tools (or `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/aeo.py`) only for fetching, rendering and checking.
Principle: *a library of answers, not a calendar of videos* – every output must answer concrete questions
in citable, self-contained sentences.

Read, once at the start and in this order:
1. `references/aeo-rules.md` – the plugin's general AEO guidelines and best practices.
2. The brand config: the plugin's `config/brand.json` merged with `~/.yt-aeo/brand.json` if it exists (channel,
   series, topics, people, site, approved footer).
3. User/brand instructions, if present: `~/.yt-aeo/guidelines.md` and every `~/.yt-aeo/guidelines/*.md`. They extend
   and override the general guidelines (tone, terminology, compliance, house style) – but never the rules the code
   enforces (YouTube limits, chapter rules, block markup, number traceability).
Pass the same instructions on to every agent you delegate to, and tell each agent explicitly: the content language
(`language_name` from `setup_status.current`) and the switched-off guideline ids (`setup_status.guidelines_off`) –
those general guidelines are not applied anywhere in the episode. Read `references/episode-schema.md` before writing `episode.json`.

## Step 0 – Set up

0. Preflight: call `setup_status`. If `configured` is false, run the `setup` skill first (brand, promo block
   and its position, guidelines), then continue here. Do this before reading the brand config below.

1. Create a task list with the steps below so the marketer sees progress.
2. Get video info with `get_video_info(url)`. Keep `title`, `upload_date`, `duration_seconds`, `thumbnail_url`,
   `current_description` (the old description – reuse its approved investor block wording, never invent promo text).
3. Create the episode folder inside the working folder: `episodes/<yyyy-mm>-<series-short>-<nn>-<slug>/`
   (e.g. `episodes/2025-09-qw-08-naem-ili-pokupka`). Use absolute paths in every tool call.

## Step 1 – Transcript

Default (manual): the user adds a transcript `.txt` file (YouTube Studio → Subtitles download, or a copy of
"Show transcript") to the episode folder or attaches it. Import it with `import_transcript(file, episode_dir)` (or
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/aeo.py import <file> <episode_dir>`).

Optional (automatic): when no file is given, call `fetch_transcript(url, episode_dir)` (uses the brand language). If it fails, do not retry endlessly: show the returned fallback
in one short message (download .vtt/.srt from YouTube Studio → Subtitles, or copy "Show transcript"), and when the
user provides the file call `import_transcript(file, episode_dir)`. A transcript pasted in the chat can be saved to a
file first and imported the same way.

If the tools are unavailable (plain chat, not a Cowork task on the computer), ask the user to paste or attach the
transcript and continue with the same steps; render with the script if Bash is available, otherwise produce the
outputs by following the templates in the `yt-description` and `wp-article` skills exactly.

## Step 2 – Edited transcript

Delegate to the `transcript-editor` agent (if agents are unavailable, do it inline following that agent's rules).
Input: `transcript.raw.txt` + `${CLAUDE_PLUGIN_ROOT}/config/glossary.json` + `~/.yt-aeo/glossary.json` (if it exists). Output: `transcript.edited.md` –
speaker-labelled paragraphs with `[MM:SS]` stamps, fillers removed, ASR errors fixed, sponsor reads wrapped in
`<!-- sponsor -->…<!-- /sponsor -->`. Meaning must never change.

## Step 3 – Knowledge map → episode.json

Delegate to the `knowledge-mapper` agent. It writes `episode.json`: proposed title options, `answer_short`,
6–8 `questions`, knowledge-based `chapters`, `claims` (fact / opinion / forecast / promo, each with timestamp and
speaker), `freshness_note`, `faq`, `key_takeaways`, article `sections`, SEO fields.

### ⏸ GATE A – facts, names, chapters, title

Stop and present to the user, compactly:
- 3 title options (question form · statement/list form · with the guest) – the chosen title becomes BOTH the
  YouTube title and the WordPress article title;
- the questions list and chapter list;
- claims needing a decision: numbers, forecasts, dated facts, anything flagged in `freshness`;
- any name/term you were unsure about.

Use AskUserQuestion for the title choice. Apply corrections to `episode.json`, set `gates.A` to
`"<name or 'user'> <ISO date>"`. If the user is not present (scheduled/unattended run), pick option 1, mark every
open item in `review.md`, leave `gates.A` empty, and continue – nothing gets pushed without the gates anyway.

## Step 4 – Write the copy

Fill the remaining prose in `episode.json` following the `yt-description` and `wp-article` skills
(answer-first, question H2s, attributed opinions, tables for comparisons, € equivalents for pre-2026 лева sums).
All description and article text lives in `episode.json` – the renderer assembles it.

## Step 5 – Render and check

1. `render_package(episode_dir)` → `youtube-description.txt`, `article.wp.html`, `schema.jsonld`, `wp-post-fields.json`.
2. `validate_package(episode_dir)` → errors / warnings / placeholders, writes `review.md`.
3. Fix every error by editing `episode.json` (never the rendered files) and re-render. Re-validate.
4. Delegate a read-through to the `aeo-reviewer` agent (5-pillar check, attribution, compliance). Apply fixes.

### ⏸ GATE B – copy & SEO

Send the user the description and article (SendUserFile) plus a 3-line summary: description length, number of
chapters/FAQ, open placeholders. Ask for edits. On approval set `gates.B`.

### ⏸ GATE C – compliance & publish go

Ask the approver to confirm: investor block unchanged from the approved template, opinions/forecasts attributed,
disclaimer present. On approval set `gates.C`.

## Step 6 – Hand-off (semi-automated)

- YouTube: tell the user to paste `youtube-description.txt` into YouTube Studio → Details → Description, set the
  chosen title, save, and check that chapters appear on the progress bar.
- WordPress: only when the user explicitly asks, call `wp_push_draft(episode_dir)` (draft only). Otherwise explain:
  new post → ⋮ → Code editor → paste `article.wp.html` → set title, slug, category, tags, SEO fields from
  `wp-post-fields.json` → Preview → Publish.
- After publishing: replace `{{ARTICLE_URL}}`-style placeholders if any, pin a YouTube comment with the article
  link, request indexing in Search Console.

Finish with one short message: what is ready, which gate is open, and the one next action.

## Never

- Never publish anything or set a post to anything but draft.
- Never invent numbers, sources, quotes or promo/investment claims; never "correct" a speaker's number silently –
  add an editorial note instead.
- Never use generic chapter titles (Интро, Разговор, Финал …).
- Never put opinions or forecasts in FAQ answers unless they are clearly attributed.
