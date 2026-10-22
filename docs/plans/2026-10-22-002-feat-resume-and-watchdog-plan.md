---
title: "feat: Checkpointed pipeline, /video2aeo:resume and watchdog"
type: feat
status: draft
date: 2026-10-22
target_version: 0.7.0
---

# feat: Checkpointed pipeline, /video2aeo:resume and watchdog

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

## Implementation units

1. `aeo_lib`: chunk split/merge, `episode_status`, `progress.json` helpers; CLI `split`, `merge`, `status`; MCP tools.
2. Agents: `transcript-editor` chunk mode (context card in, summary out); `knowledge-mapper` section mode.
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
- Cowork/Desktop cannot run the external watchdog; only R1–R6 apply there.

## Suggested order

Ship R1–R4 first (0.7.0: chunking, `episode_status`, `/video2aeo:resume` – most of the value), then hooks (R5–R6),
then the watchdog (R7) as 0.7.x because it needs real crash data to tune.
