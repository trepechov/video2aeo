# WordPress article – structure and rules

Output: `article.wp.html` (Gutenberg block markup, paste into the code editor) and `wp-post-fields.json` (title, slug,
SEO fields, category, tags). Written by `/video2aeo:wp-article`, from `work/episode.json` and the edited transcript.

The article title is **the same as the final YouTube title** (`video.title`). It lives in the knowledge-base category
(`site.kb_name`). It serves two readers at once: a person who skims (answer first, short paragraphs, headings, tables)
and an LLM that extracts (self-contained sentences, question headings, FAQ, schema).

## Block order (rendered from episode.json – never hand-write markup)

1. **YouTube embed** (core/embed, 16:9, responsive) – always the first block.
2. **Кратък отговор** – `answer_short` (class `aeo-answer`).
3. **Freshness / editorial note** – `freshness_note` (class `aeo-note`), only if needed.
4. **Основни изводи** – H2 + 5–7 bullets from `key_takeaways`, each with a number or concrete fact and its source.
5. **Съдържание на епизода** – H2 + chapter list, each linking to `watch?v=ID&t=Ns`.
6. **Body** – one `sections[]` item per question: H2 phrased as the question → 1–2 sentence answer
   (`aeo-section-answer`) → detail paragraphs → optional list / table / attributed quote → „Гледайте този момент“ link.
7. **Често задавани въпроси** – H2 + H3 question + paragraph answer, from `faq` (identical to the FAQPage schema).
8. **Транскрипт** – H2 + Details block with the edited transcript (sponsor reads removed).
9. **За авторите** – host and guest with role and 1–2 sentence bio (E-E-A-T).
10. **Още отговори от Базата знания** (label from brand config) – internal links, 3–6 items (`article.related`).
11. **Disclaimer** – from brand config.
12. **JSON-LD** – Article + VideoObject (with Clips) + FAQPage + Organization, in a Custom HTML block unless the
    SEO plugin owns the schema (`article.jsonld_in_content` in the brand config).

## Writing the sections

- 5–8 sections, 2,000–3,000 words in total including the transcript-derived parts; paragraphs ≤ 4 sentences.
- H2 = a real question people ask („Колко време отнема да научим нов език като възрастни?“).
- Open each section with the answer in 1–2 sentences that stand alone (subject named, number + year included).
- A comparison of ≥ 3 items → a table; give the source or speaker in the caption.
- Opinions and forecasts are always attributed: „Според кариерния консултант Мария Георгиева…“. Keep them out of
  `answer_short` and the FAQ unless labelled.
- Quotes: short, edited for readability without changing meaning, with speaker and timestamp.
- Pre-2026 лева sums: keep the figure, add „(≈ X €)“ at 1,95583; keep the original in `claims`.
- Do not repeat the sponsor read; the brand's call to action belongs to the brand footer or site template, not the body.
- FAQ: 5–8 entries, each 2–3 factual sentences. The visible FAQ equals the FAQPage schema (the validator checks it).

## SEO fields (`article` in episode.json → `wp-post-fields.json`)

- `slug`: Latin transliteration of the key question, 3–6 words, hyphens („kak-da-nauchim-nov-ezik“). The YouTube
  description already links to this address – once set at Gate A, do not change it.
- `seo_title` ≤ 60 chars; `meta_description` ≤ 155 chars and answer-first; one `focus_keyphrase` that appears in
  the title or first paragraph.
- `category`: `site.kb_name` from the brand config.
- The SEO plugin (Yoast, Rank Math, …) fields are filled by hand from `wp-post-fields.json`: SEO title, meta
  description, focus keyphrase. The draft push cannot set them (`manual` note in the result).

## Tags

- 3–6 tags per article, lower case, singular topic nouns people search for („подкаст“, „дистанционна работа“), never the
  guest's name or the episode number.
- Prefer tags the site already uses (they group articles); coin a new tag only when no existing one fits.
- Tags are `article.tags`; the same list feeds the schema `about` field.

## Internal links (`article.related`)

- 3–6 other knowledge-base answers on the same topic, each with title and full URL. Never invent a URL – use only
  pages the user names, pages listed in the brand config, or leave the `{{RELATED_n_URL}}` placeholders for the
  editor (the validator lists them).
- Link text is the target's question title; place at most one link per target; link from body sections only where
  the target answers a side question of that section.

## Readability check before approval

Read the rendered article top to bottom as a visitor: does the first screen answer the question? Can you skim the H2s
and understand the episode? Is every table understandable without the text around it?

## Extending

Add further rules here (image/alt-text policy, featured image, author box variants, category rules …). Brand-specific
additions belong in `~/.video2aeo/guidelines/wordpress-article.md`. The exact block markup is documented in
`skills/wp-article/references/gutenberg-blocks.md`.
