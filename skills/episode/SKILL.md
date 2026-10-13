---
name: episode
description: >
  This skill should be used when the user gives a YouTube URL of a new podcast/video episode and asks to "process the
  episode", "prepare the YouTube description", "make the AEO description with chapters", "download the subtitles and edit
  the transcript", or runs /video2aeo:episode <url>. It is the main command: subtitles → edited transcript → knowledge map
  (work/episode.json) → AEO YouTube description with chapters, with two human approval steps. The WordPress article is
  a separate follow-up command (/video2aeo:wp-article).
metadata:
  version: "0.5.1"
---

# /video2aeo:episode – transcript → knowledge map → YouTube description

**STOP – preflight, before anything else:** call `setup_status`. If `configured` is false (or the tool is missing, or
`~/.video2aeo/setup.json` is absent), do NOT read the transcript, write any text or call any other tool – run the
`setup` skill now and only then continue with the user's request. The output tools also refuse to run
(`setup_required: true`) until setup is done; if one does, stop and run the `setup` skill.

Turn one YouTube URL into an approved **YouTube description** and the shared knowledge map every other output is built
from. Write every piece of text yourself; use the `video2aeo` tools (or
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/aeo.py`) only for fetching, rendering and checking.
Principle: *a library of answers, not a calendar of videos* – every output must answer concrete questions in citable,
self-contained sentences.

Read, once at the start and in this order:
1. `${CLAUDE_PLUGIN_ROOT}/instructions/aeo-rules.md` – the general AEO principles.
2. `${CLAUDE_PLUGIN_ROOT}/instructions/youtube-description.md` – how the description, chapters and title are built.
3. The brand config: the plugin's `config/brand.json` merged with `~/.video2aeo/brand.json`.
4. User/brand instructions, if present: `~/.video2aeo/guidelines.md` and every `~/.video2aeo/guidelines/*.md`. They extend
   and override the general guidelines – but never the rules the code enforces (YouTube limits, chapter rules,
   number traceability).
Pass the same instructions on to every agent you delegate to, and tell each agent explicitly: the content language
(`language_name` from `setup_status.current`), the switched-off guideline ids (`setup_status.guidelines_off`) –
those general guidelines are not applied anywhere in the episode – and the episode's format (the base `setup_status.current.format` with the chosen profile from `current.formats` merged
over it: speakers, opening teaser, recurring segments, intro/outro wording, the free-text `notes` about the show and its `links`) plus the `coverage` plan of this episode.
The notes are the user's own background on the show: agents take them into account (audience, tone, terms, people). Read `${CLAUDE_PLUGIN_ROOT}/instructions/episode-schema.md`
before writing `episode.json`.

## Episode folder

```
episodes/<yyyy-mm>-<series-short>-<nn>-<slug>/     e.g. episodes/2026-01-show-12-episode-slug
├── youtube-description.txt      ← paste-ready outputs, for the user (this command)
├── article.wp.html, wp-post-fields.json           (/video2aeo:wp-article)
└── work/                        ← working files the user does not need to read
    ├── episode.json  transcript.raw.json  transcript.raw.txt  transcript.edited.md
    └── schema.jsonld  review.md  wp-result.json
```

Use absolute paths in every tool call. If the folder already exists with `work/episode.json`, resume from it instead
of starting over (ask which step to redo only when the user did not say).

## Step 0 – Set up

1. Preflight (STOP rule above): `setup_status` must report `configured: true`.
2. Create a task list with the steps below so the marketer sees progress.
3. **Choose the format.** If `current.formats` is empty, the base format applies. Otherwise pick the profile whose
   `series` matches the episode's series or title; if none matches clearly, ask the user once with AskUserQuestion
   (the profiles' labels, plus „основен формат“). Remember the id as `format` in `episode.json` so a resumed run
   does not ask again, and pass it as `format` to `get_video_info` / `import_transcript`.
4. `get_video_info(url, format)`. Keep the `coverage` plan (full / balanced / selective, from the real duration and the brand's episode format) – it
   decides how many questions and chapters the map keeps. Keep `title`, `upload_date`, `duration_seconds`, `thumbnail_url`, `current_description`
   (the old description – reuse its approved footer/promo wording, never invent promo text). If the page request is
   rate-limited, continue with what came back and mark the missing fields as placeholders.
5. Create the episode folder and its `work/` subfolder.

## Step 1 – Transcript

Default (manual): the user adds a transcript `.txt` (YouTube Studio → Subtitles download, or a copy of "Show
transcript") or attaches it. Import it with `import_transcript(file, episode_dir)` (or
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/aeo.py import <file> <episode_dir>`); it lands in `work/`.

Optional (automatic): when no file is given, call `fetch_transcript(url, episode_dir)`. It tries
youtube-transcript-api, then `yt-dlp` (install: `brew install yt-dlp`; optional browser cookies in
`~/.video2aeo/config.json`). If both fail, do not retry endlessly: tell the user in one short message that the transcript
must be added by hand and offer the three ways from the returned `fallback` – YouTube Studio subtitles download, "Show
transcript" copy, or an online YouTube-transcript service (paste the video address, copy/download the result) – then
wait. A transcript pasted in the chat can be saved to a file first and imported the same way.

If the tools are unavailable (plain chat, not a Cowork task on the computer), ask the user to paste or attach the
transcript and follow the same steps, producing the output by the template in `instructions/youtube-description.md`.

## Step 2 – Edited transcript

Delegate to the `transcript-editor` agent (inline following that agent's rules if agents are unavailable).
Input: `work/transcript.raw.txt` + `${CLAUDE_PLUGIN_ROOT}/config/glossary.json` + `~/.video2aeo/glossary.json` (if it
exists). Output: `work/transcript.edited.md` – speaker-labelled paragraphs with `[MM:SS]` stamps, fillers removed, ASR
errors fixed, sponsor reads wrapped in `<!-- sponsor -->…<!-- /sponsor -->`. Meaning must never change.

## Step 3 – Knowledge map → work/episode.json

Delegate to the `knowledge-mapper` agent. It writes the core of `episode.json`: title options, `answer_short`,
`context`, 6–8 `questions`, knowledge-based `chapters`, `claims` (fact / opinion / forecast / promo, each with
timestamp and speaker), `freshness_note`, `people`, hashtags and `article.slug`. The article body, FAQ and social
copy are not written here – the other commands add them to the same file later.

### ⏸ GATE A – facts, names, chapters, title

Stop and present to the user, compactly:
- 3 title options (question form · statement/list form · with the guest) – the chosen title becomes the YouTube title
  and every later output's title;
- the questions list and chapter list;
- claims needing a decision: numbers, forecasts, dated facts, anything flagged in `freshness`;
- any name/term you were unsure about;
- for a selective-tier episode: the topics that were left out, so the user can add some back.

Use AskUserQuestion for the title choice. Apply corrections to `episode.json`, set `gates.A` to
`"<name or 'user'> <ISO date>"`. If the user is not present (unattended run), pick option 1, mark every open item in
`work/review.md`, leave `gates.A` empty and continue.

## Step 4 – Write the description copy

Complete `answer_short`, `context`, `questions`, `chapters`, `freshness_note` and `hashtags` following
`instructions/youtube-description.md`. The description is rendered from these fields in a fixed order; promo, header
and footer come only from the brand config.

## Step 5 – Render and check

1. `render_package(episode_dir, outputs=["youtube"])` → `youtube-description.txt`.
2. `validate_package(episode_dir, outputs=["youtube"])` → errors / warnings / placeholders, writes `work/review.md`.
3. Fix every error by editing `work/episode.json` (never the rendered file) and re-render. Re-validate.
4. Delegate a read-through to the `aeo-reviewer` agent (answer-first, chapters, attribution, compliance of the
   description, promo block unchanged). Apply fixes.

### ⏸ APPROVAL – YouTube description

Send the user the description (SendUserFile) plus a 3-line summary: character count, number of chapters, open
placeholders. Ask for edits; confirm that the promo/footer is unchanged from the approved brand text and that opinions
and forecasts are attributed. On approval set `gates.youtube`.

## Step 6 – Hand-off

- Tell the user to paste `youtube-description.txt` into YouTube Studio → Details → Description, set the chosen title,
  save, and check that chapters appear on the progress bar.
- Next commands, same episode folder: `/video2aeo:wp-article` (knowledge-base article).

Finish with one short message: what is ready, which approval is open, and the one next action.

## Never

- Never publish anything.
- Never invent numbers, sources, quotes or promo/commercial claims; never "correct" a speaker's number silently –
  add an editorial note instead.
- Never use generic chapter titles (Интро, Разговор, Финал …).
- Never put opinions or forecasts in answers unless clearly attributed.
