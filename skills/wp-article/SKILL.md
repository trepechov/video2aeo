---
name: wp-article
description: >
  This skill should be used when the user runs /video2aeo:wp-article or asks for the WordPress / Gutenberg blog article of an
  episode that /video2aeo:episode has already processed – e.g. "write the blog article", "make the article for the
  website", "Gutenberg blocks with the video embedded first", "add FAQ and schema". It adds the article content to the
  episode's work/episode.json, renders article.wp.html and wp-post-fields.json, and stops at an approval step; an
  optional draft push to WordPress follows only on request.
metadata:
  version: "0.4.0"
---

# /video2aeo:wp-article – knowledge-base article for an episode

**STOP – preflight, before anything else:** call `setup_status`. If `configured` is false (or the tool is missing, or
`~/.video2aeo/setup.json` is absent), do NOT read the transcript, write any text or call any other tool – run the
`setup` skill now and only then continue with the user's request. The output tools also refuse to run
(`setup_required: true`) until setup is done; if one does, stop and run the `setup` skill.

The article is the **second** output of an episode. It is built from the knowledge map that `/video2aeo:episode`
created – it does not re-derive facts from the audio.

## Inputs

- The episode folder (the user names it, or take the newest under `episodes/`). It must contain `work/episode.json`
  and `work/transcript.edited.md`. If not, stop and tell the user to run `/video2aeo:episode` first.
- If `gates.A` is empty, say so and ask whether to continue anyway (facts, names and title are not yet approved).

Read, in this order: `${CLAUDE_PLUGIN_ROOT}/instructions/aeo-rules.md`,
`${CLAUDE_PLUGIN_ROOT}/instructions/wordpress-article.md`, `${CLAUDE_PLUGIN_ROOT}/instructions/episode-schema.md`, the
brand config (`config/brand.json` merged with `~/.video2aeo/brand.json`) and the user/brand instructions
(`~/.video2aeo/guidelines.md`, `~/.video2aeo/guidelines/*.md`, notably `wordpress-article.md`). Respect the switched-off
guideline ids from `setup_status.guidelines_off`.

## Steps

1. Read `work/episode.json` (questions, chapters, claims, answer, people, freshness) and the edited transcript.
2. Write into `work/episode.json` – only these fields, following `instructions/wordpress-article.md`:
   `key_takeaways`, `sections`, `faq`, and `article` (`seo_title`, `meta_description`, `focus_keyphrase`, `tags`,
   `related`, `embed_caption`; keep the existing `slug` – the YouTube description already links to it).
   The article title stays `video.title`.
3. `render_package(episode_dir, outputs=["wordpress"])` → `article.wp.html`, `wp-post-fields.json`, `work/schema.jsonld`.
4. `validate_package(episode_dir, outputs=["wordpress"])`. Fix every error in `episode.json` and re-render; never edit
   the rendered file. Placeholders for related links are listed for the editor.
5. Delegate a read-through to the `aeo-reviewer` agent (article only: answer-first, attribution, tables, FAQ/schema
   parity, compliance). Apply fixes.

### ⏸ APPROVAL – WordPress article

Send `article.wp.html` and `wp-post-fields.json` (SendUserFile) with a 3-line summary: word count of the body,
sections/FAQ count, open placeholders. Ask for edits; confirm opinions/forecasts are attributed and the disclaimer is
present. On approval set `gates.wordpress`.

## Hand-off

- Manual (default): new post → ⋮ → Code editor → paste `article.wp.html` → set title, slug, category, tags and the SEO
  plugin fields from `wp-post-fields.json` → Preview → Publish.
- Only when the user explicitly asks: `wp_push_draft(episode_dir)` – creates or updates a **draft** (never publishes;
  needs `gates.wordpress` and credentials from setup).
- After publishing: fill the `{{...}}` placeholders if any, pin a YouTube comment with the article link, request
  indexing in Search Console.

See `references/gutenberg-blocks.md` for the exact markup the renderer produces.

## Never

Never publish or set a post to anything but draft; never invent numbers, quotes, sources or related-article URLs.
