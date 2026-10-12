---
name: fb-post
description: >
  This skill should be used when the user runs /yt-aeo:fb-post or asks for a Facebook post for an episode that
  /yt-aeo:episode has already processed – e.g. "write the Facebook post", "make a social teaser for the episode". It adds
  the facebook block to the episode's work/episode.json and renders facebook-post.txt, then stops for approval.
metadata:
  version: "0.3.0"
---

# /yt-aeo:fb-post – Facebook post for an episode

**STOP – preflight, before anything else:** call `setup_status`. If `configured` is false (or the tool is missing, or
`~/.yt-aeo/setup.json` is absent), do NOT read the transcript, write any text or call any other tool – run the
`setup` skill now and only then continue with the user's request. The output tools also refuse to run
(`setup_required: true`) until setup is done; if one does, stop and run the `setup` skill.

A short teaser that gives the answer in the feed and sends readers to the article and the video. It adds no new
facts – it condenses the approved knowledge map.

## Inputs

- The episode folder (the user names it, or take the newest under `episodes/`) with `work/episode.json`. If it is
  missing, stop and tell the user to run `/yt-aeo:episode` first.
- If `gates.A` is empty, say so and ask whether to continue anyway.

Read, in this order: `${CLAUDE_PLUGIN_ROOT}/instructions/aeo-rules.md`,
`${CLAUDE_PLUGIN_ROOT}/instructions/facebook-post.md`, the brand config and the user/brand instructions
(`~/.yt-aeo/guidelines.md`, `~/.yt-aeo/guidelines/*.md`, notably `facebook-post.md`).

## Steps

1. Read `work/episode.json`: `video.title`, `answer_short`, `questions`, `claims`, and `key_takeaways` if present.
2. Write the `facebook` block into `work/episode.json` (`hook`, `points`, `question`, `hashtags`) following
   `instructions/facebook-post.md`. Every number must come from the answer, takeaways or a claim.
3. `render_package(episode_dir, outputs=["facebook"])` → `facebook-post.txt`.
4. `validate_package(episode_dir, outputs=["facebook"])`; fix errors in `episode.json` and re-render.

### ⏸ APPROVAL – Facebook post

Show the post text in chat and ask for edits. Confirm opinions/forecasts are attributed and no promo claims were added.
On approval set `gates.facebook`.

## Hand-off

Paste `facebook-post.txt` into a Facebook page post (add the video thumbnail or a clip). Posting is manual.

## Never

Never post anything; never invent numbers, quotes or promo claims.
