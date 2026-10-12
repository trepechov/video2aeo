---
name: yt-description
description: >
  This skill should be used when writing or fixing an AEO YouTube description, YouTube chapters/timestamps, or a
  YouTube title for a podcast/video episode – e.g. "write the YouTube description", "make chapters",
  "rewrite the title the way people ask AI", "the description is over 5000 characters". It defines the fixed order,
  limits and writing rules; the text is stored in episode.json and rendered by the plugin.
metadata:
  version: "0.2.2"
---

# AEO YouTube description

**STOP – preflight, before anything else:** call `setup_status`. If `configured` is false (or the tool is missing, or
`~/.yt-aeo/setup.json` is absent), do NOT read the transcript, write any text or call any other tool – run the
`setup` skill now and only then continue with the user's request. The output tools also refuse to run
(`setup_required: true`) until setup is done; if one does, stop and run the `setup` skill.

Write the description fields in `episode.json`; `render_package` assembles them in this fixed order. The brand's
fixed **header** (`description.header`, if set) always comes first, verbatim – never write or reword it:

1. `answer_short` – 2–3 sentences that directly answer the episode's main question. Reads like the first lines of an
   article. Must make sense without the video. Contains the key fact(s) with dates.
2. `context` – 1–2 sentences: series, host, guest (with role), what is covered.
3. „Основни въпроси, на които ще получите отговор:“ – rendered from `questions[].q` (5–6 shown best).
4. Article link – built from `article.slug` and the brand config (`<site.base_url>/<site.kb_path>/<slug>/`).
5. „⏱️ Глави:“ – rendered from `chapters`.
6. `freshness_note` (if any).
7. Host / guest line – from `people`.
8. Brand footer – from the brand config (`~/.yt-aeo/brand.json` over `config/brand.json`) (schedule, short
   disclaimer + link, socials). The promo block (links, messages, ads – `description.promo`) is rendered at the
   end, inside the footer, or at the very top when `description.promo_position` is `top` (the answer then starts
   below it). Never write or reword the promo text yourself.
9. Up to 3 `hashtags` (YouTube shows the first three above the title).

## Chapters

- First chapter `t: 0`; at least 3; strictly ascending; each ≥ 10 s; one per distinct question; ~1 per 2–4 minutes
  (a 50-minute episode: 12–22).
- Title = the question or the knowledge the segment gives: „Защо рекордните депозити не са добра новина“, not „Депозити“.
- ≤ 70 characters (the first 49 show on hover). Bulgarian sentence case, no emoji, no trailing period.
- Do not start a chapter inside a sponsor read; let the previous chapter cover it.
- Take timestamps from the transcript stamps; round down to the start of the sentence that opens the topic.

## Title (shared with the article)

Offer three options at Gate A: (1) the main question, (2) a statement/list, (3) the expert framing.
Key question in the first ~60 characters, series and number at the end: „… | <series> Еп. 8“. No ALL CAPS,
no „ШОК“, no clickbait the episode does not deliver.

## Limits

- ≤ 5,000 characters after placeholders are filled; keep ≥ 100 characters of margin.
- No `<` or `>` (YouTube rejects them – the renderer replaces them).
- If over the limit: shorten `context`, cut questions to 5, merge adjacent short chapters, then ask the brand owner to
  shorten the footer (move the full disclaimer to the website and link it).

See `references/example-demo.txt` for a complete rendered example (fictional demo brand).
