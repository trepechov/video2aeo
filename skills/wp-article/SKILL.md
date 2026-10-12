---
name: wp-article
description: >
  This skill should be used when writing the WordPress / Gutenberg blog article for a podcast/video episode –
  e.g. "write the blog article", "make the article for the website", "Gutenberg blocks with the video embedded first",
  "add FAQ and schema", "make the article readable for people and AI". It defines block order, section writing rules,
  SEO fields and schema; the text goes into episode.json and the plugin renders valid block markup.
metadata:
  version: "0.2.1"
---

# AEO WordPress article

**STOP – preflight, before anything else:** call `setup_status`. If `configured` is false (or the tool is missing, or
`~/.yt-aeo/setup.json` is absent), do NOT read the transcript, write any text or call any other tool – run the
`setup` skill now and only then continue with the user's request. The output tools also refuse to run
(`setup_required: true`) until setup is done; if one does, stop and run the `setup` skill.

The article title is **the same as the final YouTube title** (`video.title`). It lives in the knowledge-base category (`site.kb_name` in the brand config).
It must serve two readers at once: a person who skims (answer first, short paragraphs, headings, tables) and an
LLM that extracts (self-contained sentences, question headings, FAQ, schema).

## Block order (rendered from episode.json – do not hand-write markup)

1. **YouTube embed** (core/embed, 16:9, responsive) – always the first block.
2. **Кратък отговор** – `answer_short` in a paragraph with class `aeo-answer`.
3. **Freshness / editorial note** – `freshness_note` (class `aeo-note`), only if needed.
4. **Основни изводи** – H2 + 5–7 bullets from `key_takeaways`, each with a number or concrete fact.
5. **Съдържание на епизода** – H2 + chapter list, each linking to `watch?v=ID&t=Ns`.
6. **Body** – one `sections[]` item per question: H2 phrased as the question → 1–2 sentence answer
   (`aeo-section-answer`) → detail paragraphs → optional list / table / attributed quote → "Гледайте този момент" link.
7. **Често задавани въпроси** – H2 + H3 question + paragraph answer, from `faq` (identical to FAQPage schema).
8. **Транскрипт** – H2 + Details block with the edited transcript (sponsor reads removed).
9. **За авторите** – host and guest with role and 1–2 sentence bio (E-E-A-T).
10. **Още отговори от Базата знания** (label from brand config) – internal links (`article.related`), 3–6 items.
11. **Disclaimer** – from brand config.
12. **JSON-LD** – Article + VideoObject (with Clips) + FAQPage + Organization, in a Custom HTML block unless the
    SEO plugin owns schema (`article.jsonld_in_content` in brand config).

## Writing the sections

- 5–8 sections, 2,000–3,000 words total including the transcript summary parts; paragraphs ≤ 4 sentences.
- H2 = a real question people ask („Колко данък върху имотите плащат собствениците в България?“).
- Open each section with the answer in 1–2 sentences that stand alone (subject named, number + year included).
- Any comparison of ≥ 3 items → a table (countries, rates, options). Give the source/speaker in the caption.
- Opinions and forecasts are always attributed: „Според финансовия консултант Мария Георгиева…“. Keep them out of
  `answer_short` unless labelled.
- Quotes: short, edited for readability without changing meaning, with speaker and timestamp.
- Pre-2026 лева sums: keep the figure, add „(≈ X €)“ at 1,95583 – but keep the original in `claims`.
- Do not repeat the sponsor read; the investor CTA belongs to the brand footer/site template, not the body.

## SEO fields (`article`)

- `slug`: Latin transliteration of the key question, 3–6 words, hyphens („imotni-danatsi-politika-ceni“).
- `seo_title` ≤ 60 chars, `meta_description` ≤ 155 chars and answer-first, one `focus_keyphrase`.
- `category`: `site.kb_name` from the brand config; `tags`: 3–6 topic tags.

## Readability check before Gate B

Read the rendered article top to bottom as a visitor: does the first screen answer the question? Can you skim the
H2s and understand the episode? Is every table understandable without the text around it?

See `references/gutenberg-blocks.md` for the exact markup the renderer produces and how to paste it.
