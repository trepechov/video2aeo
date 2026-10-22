---
title: "feat: Checkpointed pipeline, resume, watchdog and per-task models"
type: feat
status: active  # 0.7.0: units 1-3, 6, 7 (chunking, episode_status, resume, models) shipped; hooks and watchdog open
date: 2026-10-22
target_version: 0.7.0
---

# feat: Checkpointed pipeline, resume, watchdog and per-task models

## Summary

Long episodes make the run slow and sometimes crash Claude Code. Today the only "resume" is one sentence in the
`episode` skill ("if `work/episode.json` exists, resume") – it cannot tell which step finished, and the two heavy steps
(`transcript-editor`, `knowledge-mapper`) each process the whole transcript in a single agent call, so a crash loses
everything. Fix in three layers: **checkpoint** (small units of work that survive a crash), **resume** (one command that
continues from disk state), **watchdog** (something outside the model that notices a stall/crash and re-launches resume).

## Problem Frame

- Cause of slowness and crashes is the same: one agent call over a 2–3 h transcript (very large context, minutes of
  generation, no intermediate output on disk).
- A crash today means: no record of the step, partial or missing `transcript.edited.md`, the user re-runs by hand.
- Claude cannot restart itself after the process dies, so the watchdog must live outside the session.

## Requirements

- R1. Transcript editing works on chunks; each finished chunk is a file on disk. A crash loses at most one chunk.
- R2. Pipeline state is **derived from files** by code (`episode_status`), not remembered by the model. Optional
  `work/progress.json` only records timestamps, attempt counts and the last error.
- R3. `/video2aeo:resume [episode_dir]` reads `episode_status`, tells the user in one line where it continues, and runs
  only the remaining steps. With no argument it finds the most recently modified unfinished episode under the episodes root.
- R4. Resume never redoes approved work and never skips a human gate (`gates.A`, `gates.youtube`, `gates.wordpress`).
- R5. A `Stop` hook refuses to end a turn while a step is mid-way and no gate is pending ("continue with chunk 7/12"),
  with a loop guard (`stop_hook_active`) so it cannot spin.
- R6. A `SessionStart` hook mentions an unfinished episode and suggests `/video2aeo:resume` (no auto-run).
- R7. `scripts/watchdog.py` (stdlib, Python 3.9, cross-platform) runs the pipeline headless, kills it after a stall
  timeout, and relaunches `resume` up to N times with back-off. Stops at a human gate and reports it.
- R9. Every delegated operation runs on the cheapest model that is good enough for it, whatever model the user has
  pre-selected. Mapping lives in config, not in prose; the plugin's default table applies out of the box; the user may optionally switch profile (`fast` / `balanced` / `quality`) or pin single operations.
- R8. All of it works unattended and attended; nothing publishes (principle 3).

## Design

### 1. Chunking (also the speed-up)

- `split_transcript(episode_dir, minutes=10)` → `work/chunks/NN.raw.txt` split on paragraph stamps, 20–30 s overlap
  context line (not duplicated in output), plus `work/chunks/index.json` (n, start, end, status).
- `transcript-editor` gets one chunk per call plus a fixed "context card" (speakers, glossary hits so far, teaser/sponsor
  state from earlier chunks) and writes `work/chunks/NN.edited.md`. Chunks are independent, so the skill may run 3–4
  agents in parallel → faster than today even without crashes.
- `merge_transcript` concatenates in order, checks stamps are monotonic and none is missing/duplicated, writes
  `transcript.edited.md`, and marks chunks done. Teaser/sponsor/boilerplate markers that span a chunk border are fixed
  here (code), the first chunk's teaser decision is passed to the rest.
- `knowledge-mapper` for long episodes: per-section notes first (`work/map/NN.json`: claims, questions candidates,
  people), then one small merge call that builds `episode.json`. Same checkpointing.

### 2. `episode_status` (code-enforced state)

New tool/CLI `episode_status(episode_dir)` returns:

```
{ "step": "edit_transcript", "done": ["info","transcript"], "chunks": {"total": 12, "done": 7, "failed": [8]},
  "pending_gate": null, "next_action": "edit chunks 8-12", "stale": false }
```

Steps in order: `info → transcript → edit_transcript → knowledge_map → gate_A → description → validate → gate_youtube →
done`. A step is done when its output exists **and** validates (e.g. edited transcript covers the raw stamps; `episode.json`
parses). `stale` = files older than the input they were built from (raw transcript replaced) → ask before reusing.
`workspace_status` from plan 001 is reused for locating the episode.

### 3. `/video2aeo:resume` skill

Thin: setup preflight, `episode_status`, announce, jump into the matching step of the `episode` / `wp-article` skill
(the step texts stay in one place; `episode` skill's Step 0 is changed to call `episode_status` instead of the prose rule).
Unattended flag `--unattended` (used by the watchdog) makes the Gate A rule "pick option 1, log to `review.md`, stop at
the approval" already described in the `episode` skill explicit.

### 4. Hooks (`hooks/hooks.json`)

- `SessionStart` → `scripts/aeo.py hook session-start`: prints one line if an unfinished episode exists.
- `Stop` → `scripts/aeo.py hook stop`: if `episode_status` says a non-gate step is mid-way and the transcript of this
  turn did not end in a question to the user, return `{"decision":"block","reason":"Continue: <next_action>"}`.
  Guard: honour `stop_hook_active`, and a counter in `progress.json` (max 3 consecutive blocks per step).
- Limits: hooks do not fire when the process dies; that is the watchdog's job. Hooks load in Claude Code and Cowork only.

### 5. Watchdog `scripts/watchdog.py`

```
python3 scripts/watchdog.py <episode_dir | url> [--stall-minutes 8] [--max-restarts 5] [--model ...]
```

Loop: launch `claude -p "/video2aeo:resume <dir> --unattended" --plugin-dir <plugin> --output-format stream-json`,
read the stream, and treat as stalled when no output event **and** no file under `work/` changed for `stall-minutes`.
On stall/non-zero exit: terminate the process tree, record the attempt in `progress.json`, wait (30 s, 2 min, 5 min…),
relaunch. After each exit call `episode_status`: `done` or `pending_gate` → stop and print what is waiting; same step
failing 3 times → stop and write `work/watchdog.log` with the diagnosis (smaller chunk size is suggested automatically:
the next attempt runs with `minutes=5`). Needs `claude` on PATH; desktop app users get the Stop hook + manual
`/video2aeo:resume` only (state this in the docs).

### 6. Model per operation

Problem: all three agents have `model: inherit`, so a user who has the most powerful (and slowest) model selected pays
for it on mechanical chunk editing too. The setup skill currently says the plugin cannot switch models – true for the
**session** model, but not for **delegated** work: the Agent tool accepts a `model` per call, and agent frontmatter has a default.

| Operation | Nature | `fast` | `balanced` (default) | `quality` |
|---|---|---|---|---|
| `transcript_edit` (per chunk) | mechanical, long output, Bulgarian | haiku | sonnet | sonnet |
| `knowledge_map_sections` (per section) | extraction | sonnet | sonnet | opus |
| `knowledge_map_merge` (titles, questions, chapters) | judgement, small input | sonnet | opus | opus |
| `description_copy` (answer, context, FAQ text) | writing quality matters | inherit | inherit | inherit |
| `aeo_review` | checklist read-through | haiku | sonnet | sonnet |

(Initial guess – validated by the benchmark below, then frozen. Values are aliases `haiku|sonnet|opus|fable|inherit`, so they
follow new model releases without a plugin update. Full model ids are not accepted: the Agent tool takes aliases only. The article
is written by the session model, so there is no separate article operation.)

- **Default = plugin defaults.** With no user config, the `balanced` table in `config/models.json` applies. Setup does
  **not** ask about models; a fresh install just works. Nothing the user must decide.
- **Optional override**, two levels, both stored in `~/.video2aeo/config.json` under `models`:
  - `{"profile": "fast" | "balanced" | "quality"}` – switch the whole table;
  - `{"overrides": {"transcript_edit": "haiku", ...}}` – pin single operations (alias; `inherit` = use
    the session model).
  Precedence: per-operation override > profile > plugin default. Absent keys fall through, so a partial override
  never breaks the rest.
- **How the user sets it:** on request only – `/video2aeo:setup` offers "change models" when the user asks for it
  (profiles in plain words with rough time impact, then optional per-operation pins); or edit `config.json` by hand.
  `setup_status.models` returns the resolved table plus `source` per operation (`default|profile|override`) so the
  skill can show what is in effect.
- **Validation:** code merges and validates (unknown operation, profile or alias → error naming the key; the bad entry is ignored and
  the default used, so a typo never stops an episode). Overrides never touch code-enforced rules.
- **Use:** skills pass `model=setup_status.models.operations.<operation>.model` on every Agent call; agent frontmatter defaults become
  `sonnet` (works even when a skill forgets). `inherit` is kept only for the writing step done in the main session.
- **Session model warning:** `episode_status` returns `session_model_hint` (read from the agent's own context by the
  skill). If the session is on the heaviest tier and the profile is `fast`/`balanced`, the skill says once: "the session
  model is only used for the final copy – you can switch to <lighter> with /model to save time". It never blocks.
- **Watchdog:** passes `--model` from the same table for the headless run (session model = `description_copy`).
- **Reasoning effort:** where the harness exposes it per agent/skill, mechanical operations use low effort; recorded in
  the same table (`effort`), ignored silently when unsupported.
- **Fallback on failure:** if a delegated call fails or `merge_transcript`/schema validation rejects the output twice,
  retry once one tier up (`haiku→sonnet→opus`), log it in `progress.json`. Code decides, not the model.
- **Benchmark before freezing the table:** run `transcript_edit` and `knowledge_map_*` on 2–3 back-catalogue episodes
  with each alias; compare wall time, token cost and Bulgarian quality (names, numbers unchanged – `validate_package`
  number traceability is an objective check). Keep the cheapest passing choice per operation.

## Implementation units

1. `aeo_lib`: chunk split/merge, `episode_status`, `progress.json` helpers; CLI `split`, `merge`, `status`; MCP tools.
2. `config/models.json`, merge in `setup_status`, `models` in setup/`save_setup`; agent frontmatter defaults; model fallback in `progress.json`. Agents: `transcript-editor` chunk mode (context card in, summary out); `knowledge-mapper` section mode.
3. Skills: `episode` Step 2/3 chunk loop and `episode_status` at Step 0; new `resume` skill.
4. Hooks + `hooks/hooks.json` (check `claude plugin validate .` accepts it; no top-level `bin/`).
5. `scripts/watchdog.py` + `dev/` test with a fake `claude` executable that hangs/crashes on cue.
6. Docs: `README`, `docs/plugin-build-plan.md` roadmap line, CLAUDE.md layout/status.
7. Tests in `dev/smoke.py` on the fictional fixture (3.14 and 3.9): kill after chunk 3 → status reports chunks 4..n,
   merge detects a missing stamp, stale detection, Stop-hook loop guard, watchdog with the fake `claude`.

## Risks / open questions

- Chunk borders: speaker continuity and sentence cut at the border. Mitigation: cut only at paragraph stamps, pass the
  last paragraph of the previous chunk as read-only context.
- Quality difference chunked vs. whole: compare on 2 back-catalogue episodes before making chunking the default for
  short episodes (below ~25 min keep one call).
- Is the crash a Claude Code bug, memory/context exhaustion or an API timeout? Chunking fixes the last two; ask the user
  to attach `claude` logs next time it crashes so the watchdog's stall rule can be tuned.
- The Stop hook may fight an interactive user who wants to stop: it only blocks inside a pipeline step, never at gates.
- Model aliases map to whatever the user's plan offers; if an alias is unavailable the call fails → fallback tier or `inherit`.
- Cowork/Desktop cannot run the external watchdog; only R1–R6 apply there.

## Suggested order

Ship R1–R4 and R9 first (0.7.0: chunking, `episode_status`, `/video2aeo:resume`, model table – most of the value), then hooks (R5–R6),
then the watchdog (R7) as 0.7.x because it needs real crash data to tune.
