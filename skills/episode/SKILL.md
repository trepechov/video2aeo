---
name: episode
description: >
  This skill should be used when the user gives a YouTube URL of a new podcast/video episode and asks to "process the
  episode", "prepare the YouTube description", "make the AEO description with chapters", "download the subtitles and edit
  the transcript", or runs /video2aeo:episode <url>. It is the main command: subtitles → edited transcript → knowledge map
  (work/episode.json) → AEO YouTube description with chapters, with two human approval steps. The WordPress article is
  a separate follow-up command (/video2aeo:wp-article).
metadata:
  version: "0.10.0"
---

# /video2aeo:episode – transcript → knowledge map → YouTube description

**STOP – preflight, before anything else:** run `pwd` and call `setup_status(cwd)`. If the tool is missing or fails to
start, the helper is not running: follow the `doctor` skill yourself (do not just tell the user to run it) and continue
once the tools work. If `project_choice_needed` is true, ask once which project to use (names from `projects`) and call
`setup_status(cwd, project=<id>)`. If `configured` is false (or `needs_review` is true), do NOT read the transcript,
write any text or call any other tool – run the `setup` skill now and only then continue with the user's request. Say
the project once at the start („Проект: ‹project.name›“) so a wrong one is noticed. Pass `cwd` to every later tool
call. A `project_mismatch` error means the episode belongs to another project: stop and tell the user. The settings
folder below is `setup_status.settings_dir`. The output tools also refuse to run
(`setup_required: true`) until setup is done; if one does, stop and run the `setup` skill.

**Then check the working folder:** run `pwd` and call `workspace_status(cwd)`. When `ok` is false (`suspicious`,
`unknown` or `no_root`), STOP before reading the transcript or creating anything: tell the user in one or two sentences
(in the content language) what `reason` and `next_step` say – typically „Отворете задачата отново с избрана папката
на епизодите: <episodes_root>“ – and wait. Do not offer to work in the current folder anyway; only if the user
explicitly insists, continue and pass `allow_outside_root: true` to the output tools. When `status` is
`inside_episode`, that `episode_dir` is the folder to resume.

Turn one YouTube URL into an approved **YouTube description** and the shared knowledge map every other output is built
from. Write every piece of text yourself; use the `video2aeo` tools (or
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/aeo.py`) only for fetching, rendering and checking.
Principle: *a library of answers, not a calendar of videos* – every output must answer concrete questions in citable,
self-contained sentences.

Read, once at the start and in this order:
1. `${CLAUDE_PLUGIN_ROOT}/instructions/aeo-rules.md` – the general AEO principles.
2. `${CLAUDE_PLUGIN_ROOT}/instructions/youtube-description.md` – how the description, chapters and title are built.
3. The brand config: the plugin's `config/brand.json` merged with `<settings folder>/brand.json`.
4. User/brand instructions, if present: `<settings folder>/guidelines.md` and every `<settings folder>/guidelines/*.md`. They extend
   and override the general guidelines – but never the rules the code enforces (YouTube limits, chapter rules,
   number traceability).
Models: every agent call gets the model of its operation from `setup_status.models.operations.<operation>.model`
(`transcript_edit`, `knowledge_map_sections`, `knowledge_map_merge`, `aeo_review`) as the Agent tool's `model`; `inherit`
means leave `model` out. Never choose a model yourself and never pick a heavier one "to be safe" – the defaults are tuned
for speed. If a delegated call fails or its output is rejected twice, retry once with that operation's `fallback` model
and note it (`progress_note`). If `models.errors` is not empty, mention it once; the defaults are used for the bad entries.
Pass the same instructions on to every agent you delegate to, and tell each agent explicitly: the settings folder
(`setup_status.settings_dir` – the agents read the brand files there), the content language
(`language_name` from `setup_status.current`), the switched-off guideline ids (`setup_status.guidelines_off`) –
those general guidelines are not applied anywhere in the episode – and the episode's format (the base `setup_status.current.format` with the chosen profile from `current.formats` merged
over it: speakers, opening teaser, recurring segments, intro/outro wording, the free-text `notes` about the show and its `links`) plus the `coverage` plan of this episode.
The notes are the user's own background on the show: agents take them into account (audience, tone, terms, people). Read `${CLAUDE_PLUGIN_ROOT}/instructions/episode-schema.md`
before writing `episode.json`.

## Episode folder

The path is built by code, never by you: `episode_path(slug, format, upload_date, number?)` creates
`<episodes root>/<series folder>/<yyyy-mm>-<series>-<nn>-<slug>/` (series folder = the format profile's `folder`,
`_other` for the base format) and returns it as `episode_dir`. Use that exact path in every tool call; the output tools
refuse any other location (`wrong_folder`).

```
<episode_dir>/
├── youtube-description.txt      ← paste-ready outputs, for the user (this command)
├── article.wp.html, wp-post-fields.json           (/video2aeo:wp-article)
└── work/                        ← working files the user does not need to read
    ├── episode.json  transcript.raw.json  transcript.raw.txt  transcript.edited.md
    └── schema.jsonld  review.md  wp-result.json
```

If the folder already exists with `work/episode.json` (or the session is inside it), resume from it instead of
starting over (ask which step to redo only when the user did not say).

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
5. Create the episode folder with `episode_path` (short Latin `slug` from the title; leave `number` out unless the
   user or the title gives one) and **say where the files will go** before the first write, e.g.
   „📁 Файловете ще се запазят в: <episode_dir>“. If the user corrects the series or the number, call `episode_path`
   again for the right folder (an unused empty folder may stay).

## Step 1 – Transcript

Default (manual): the user adds a transcript `.txt` (YouTube Studio → Subtitles download, or a copy of "Show
transcript") or attaches it. Import it with `import_transcript(file, episode_dir)` (or
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/aeo.py import <file> <episode_dir>`); it lands in `work/`.

Optional (automatic): when no file is given, call `fetch_transcript(url, episode_dir)`. It tries
youtube-transcript-api, then `yt-dlp` (optional browser cookies in `~/.video2aeo/config.json`, for every project).
- **`missing_subtitle_tools` is in the result** – no download tool is installed, so YouTube was never asked. Do not
  make the user open a terminal: make the one-question offer of the `setup` skill's last step (same wording, same
  rules). On yes call `install_subtitle_tools`; on `ok: true` call `fetch_transcript` again once. On no, or `ok: false`
  (show `manual_command` in one line), use the manual route below.
- If both tools are installed and both fail, do not retry endlessly: tell the user in one short message that the transcript
must be added by hand and offer the three ways from the returned `fallback` – YouTube Studio subtitles download, "Show
transcript" copy, or an online YouTube-transcript service (paste the video address, copy/download the result) – then
wait. A transcript pasted in the chat can be saved to a file first and imported the same way.

If the tools are unavailable (plain chat, not Claude Code mode on the computer), ask the user to paste or attach the
transcript and follow the same steps, producing the output by the template in `instructions/youtube-description.md`.

## Step 2 – Edited transcript (in chunks, resumable)

The transcript is edited chunk by chunk so a crash or a timeout loses at most one chunk.

1. `split_transcript(episode_dir)` → `work/chunks/NN.raw.txt` (+ `NN.context.txt`, the end of the previous chunk, read-only).
   Episodes under 25 minutes are one chunk and follow the same steps. Calling it again is safe.
2. Delegate **chunk 1 alone** to the `transcript-editor` agent (`model` = `transcript_edit`): it finds the speakers, the teaser
   and the first sponsor read, and writes `work/chunks/01.edited.md` including the `# Транскрипт – <title>` header. Give it the
   chunk number, the paths, the glossary files, the language, the switched-off guideline ids and the format. Keep its report.
3. Delegate the remaining chunks with the same inputs plus a short context card (speakers with roles as reported by chunk 1,
   teaser range, glossary fixes found so far). Run up to 3 agents in parallel, one message with several Agent calls, then the
   next batch. Each agent writes only its own `NN.edited.md`.
4. Call `episode_status`. A chunk listed as `invalid` or `todo` is redone once (`progress_note` step `chunk-NN` with the
   error; second try with the operation's `fallback` model). If a chunk still fails, `split_transcript(minutes=<half, ≥ 3>)`
   – chunks with unchanged text are kept – and edit what is left. Stop and report after that.
5. `merge_transcript(episode_dir)` → `work/transcript.edited.md`. It refuses until every chunk is complete and checks stamps,
   length and markers. Show its `warnings` and the agents' reports (suspicious numbers, `[?]` places) at Gate A.

Without agents, follow `agents/transcript-editor.md` yourself, chunk by chunk, with the same files.

## Step 3 – Knowledge map → work/episode.json

Delegate to the `knowledge-mapper` agent. It writes the core of `episode.json`: title options, `answer_short`,
`context`, 6–8 `questions`, knowledge-based `chapters`, `claims` (fact / opinion / forecast / promo, each with
timestamp and speaker), `freshness_note`, `people`, hashtags and `article.slug`. The article body, FAQ and social
copy are not written here – the other commands add them to the same file later.

- **One chunk (short episode):** one call, `model` = `knowledge_map_merge`, mode "whole episode".
- **Several chunks:** first section mode – one call per chunk (`model` = `knowledge_map_sections`, up to 3 in parallel) that
  reads `work/chunks/NN.edited.md` and writes `work/map/NN.json`; then one merge call (`model` = `knowledge_map_merge`) that
  reads `work/map/*.json` (and the transcript for spot checks) and writes `work/episode.json`. `episode_status` shows which
  sections are missing after a crash.

### ⏸ GATE A – facts, names, chapters, title

Stop and present to the user, compactly:
- 3 title options (question form · statement/list form · with the guest) – the chosen title becomes the YouTube title
  and every later output's title;
- the questions list and chapter list;
- claims needing a decision: numbers, forecasts, dated facts, anything flagged in `freshness`;
- any name/term you were unsure about;
- for a selective-tier episode: the topics that were left out, so the user can add some back.

Use AskUserQuestion for the title choice. Apply corrections to `episode.json`, set `gates.A` to
`"<name or 'user'> <ISO date>"`. If the user is not present (unattended run, e.g. started by the watchdog), pick option 1,
mark every open item in `work/review.md`, leave `gates.A` empty, call `progress_note(step="gate_A", defer_gate="A")` so
`episode_status` moves on, and continue. The gate stays listed under `open_gates` until a human sets it.

## Step 4 – Write the description copy

Complete `answer_short`, `context`, `questions`, `chapters`, `freshness_note` and `hashtags` following
`instructions/youtube-description.md`. The description is rendered from these fields in a fixed order; promo, header
and footer come only from the brand config.

## Step 5 – Render and check

1. `render_package(episode_dir, outputs=["youtube"])` → `youtube-description.txt`.
2. `validate_package(episode_dir, outputs=["youtube"])` → errors / warnings / placeholders, writes `work/review.md`.
3. Fix every error by editing `work/episode.json` (never the rendered file) and re-render. Re-validate.
4. Delegate a read-through to the `aeo-reviewer` agent (`model` = `aeo_review`; answer-first, chapters, attribution, compliance of the
   description, promo block unchanged). Apply fixes.

### ⏸ APPROVAL – YouTube description

Send the user the description (SendUserFile) plus a 3-line summary: character count, number of chapters, open
placeholders. Ask for edits; confirm that the promo/footer is unchanged from the approved brand text and that opinions
and forecasts are attributed. On approval set `gates.youtube`. In an unattended run stop here instead: never set
`gates.youtube` yourself, call `progress_note(step="gate_youtube", defer_gate="youtube")` and report that the description
is ready for approval.

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
