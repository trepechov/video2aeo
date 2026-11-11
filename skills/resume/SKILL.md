---
name: resume
description: >
  This skill should be used when the user runs /video2aeo:resume, or says that an episode run crashed, froze, timed out
  or stopped half way and asks to "continue", "resume", "pick up where it stopped" or "finish the episode". It reads what
  is already on disk, says where the episode stands and continues with only the remaining steps – never redoing approved
  work and never skipping an approval.
metadata:
  version: "0.10.0"
---

# /video2aeo:resume – continue an interrupted episode

**STOP – preflight:** run `pwd` and call `setup_status(cwd)`. If the tool is missing or fails, follow the `doctor` skill
first; if `project_choice_needed` is true, ask which project and call `setup_status(cwd, project=<id>)`; if `configured`
is false, run the `setup` skill first. With a folder argument, the episode's own project is used; a `project_mismatch`
error means it belongs to another project – say so and stop. Pass `cwd` to every later tool call and tell every agent
you delegate to the settings folder (`setup_status.settings_dir`), as the `episode` skill does.

Arguments: an optional episode folder (absolute path) and the word `--unattended` (used by automated restarts: nobody
answers questions).

1. **Find the episode.** With a folder argument, use it. Otherwise call `episode_status()` without arguments: it returns the
   most recently touched unfinished episode under the episodes root. If it returns `step: "none"`, say that nothing is
   waiting and offer `/video2aeo:episode <url>` for a new episode. If you are unsure it is the right one (the user
   mentioned another title), ask once with AskUserQuestion, listing the folder name.
2. **Say where it stands**, in one or two lines the marketer understands: the episode folder name, what is finished, what
   comes next (`next_action`, chunk progress such as „7 от 12 части са редактирани“), and any `open_gates` that still wait for a
   human. If `last_error` is set, include it. If `stale` is true, say the transcript changed after it was split and that
   finished parts with unchanged text are kept.
3. **Continue** by following the `episode` skill (`${CLAUDE_PLUGIN_ROOT}/skills/episode/SKILL.md`) from the step named in
   `step`, with the same rules (models per operation from `setup_status.models`, chunked editing, gates). Skip every step in
   `done`. Do not re-read or re-edit finished chunks. Only the `episode` skill's steps exist – this skill adds none.
4. **Stop** at the same places as `episode`: Gate A and the YouTube description approval. With `--unattended`, defer the gate
   (`progress_note` with `defer_gate`) as the `episode` skill describes and end with a report instead of asking.
5. If `attempts` for the current step is 3 or more, do not retry: report the step and `last_error`, and suggest a smaller
   chunk size (`split_transcript` with `minutes` 5) or adding the transcript by hand.

If the article was already started (`article` is `content_ready` or `rendered` in the status), mention
`/video2aeo:wp-article`; resume itself only finishes the YouTube description.

Finish with one short message: what was completed now, which approval is open, and the one next action.
