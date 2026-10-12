# episode.json – the single source of truth

Every output is rendered from this file, so description, article, schema and social posts can never disagree.
Edit this file, then re-run `render_package`. Never hand-edit rendered files.

**Location:** `<episode folder>/work/episode.json`. The episode folder holds only the paste-ready outputs
(`youtube-description.txt`, `article.wp.html`, `wp-post-fields.json`, `facebook-post.txt`); `work/` holds the working
files (this file, `transcript.raw.*`, `transcript.edited.md`, `schema.jsonld`, `review.md`, `wp-result.json`).

**Who writes what** (each command adds its own block and never rewrites another's):

| Command | Fields |
|---|---|
| `/yt-aeo:episode` | everything up to `hashtags`: `video`, `series`, `people`, `answer_short`, `context`, `questions`, `chapters`, `claims`, `freshness_note`, `hashtags`, `article.slug` (+ `article.category`), `gates.A`, `gates.youtube` |
| `/yt-aeo:wp-article` | `key_takeaways`, `sections`, `faq`, `article.*` (SEO fields, tags, related), `gates.wordpress` |
| `/yt-aeo:fb-post` | `facebook`, `gates.facebook` |

Text fields accept light markdown: `**bold**`, `*italic*`, `[text](https://url)`. No raw HTML.
Times (`t`) are **seconds** (integers). Unknown values: use `{{UPPER_SNAKE}}` placeholders – the validator lists them.

```jsonc
{
  "schema_version": "1.0",
  "video": {
    "id": "11-char YouTube id",
    "title": "FINAL title – used for YouTube AND the WordPress post",
    "original_title": "title as uploaded",
    "title_options": ["question form", "statement/list form", "with guest"],
    "upload_date": "2025-09-17T19:00:00+03:00",
    "duration_seconds": 3010,
    "thumbnail_url": "https://i.ytimg.com/vi/<id>/maxresdefault.jpg"
  },
  "series": "Въпрос на седмицата",
  "episode_number": 8,
  "people": [
    {"name": "Иван Петров", "role": "host", "job_title": "…", "url": "…", "bio": "1–2 sentences, E-E-A-T"},
    {"name": "Мария Георгиева", "role": "guest", "job_title": "финансов консултант", "bio": "…"}
  ],
  "answer_short": "2–3 sentences: the direct answer to the episode's main question. Citable on its own.",
  "context": "1–2 sentences: format, host, guest, what is covered.",
  "questions": [
    {"q": "Natural question people ask an AI", "a": "1-sentence answer", "chapter_t": 62}
  ],
  "chapters": [ {"t": 0, "title": "Knowledge title"}, {"t": 62, "title": "…"} ],
  "key_takeaways": ["5–7 bullets, each with a concrete number/fact and its source"],
  "sections": [
    {
      "h2": "Question as heading?",
      "anchor": "optional-latin-anchor",
      "answer": "1–2 sentence direct answer (rendered first, class aeo-section-answer)",
      "paragraphs": ["detail …", "…"],
      "bullets": ["optional"], "ordered": false,
      "table": {"headers": ["Държава", "Годишен данък"], "rows": [["България", "0,01–0,45%"]], "caption": "Източник: …"},
      "quotes": [{"text": "short verbatim (edited) quote", "speaker": "Мария Георгиева", "t": 2340}],
      "chapter_t": 62
    }
  ],
  "faq": [ {"q": "…?", "a": "2–3 sentence factual answer; opinions only if attributed"} ],
  "claims": [
    {"text": "Депозитите на домакинствата надхвърлят 94 млрд. лв. (юли 2025)", "t": 1162,
     "speaker": "Иван Петров", "type": "fact|opinion|forecast|promo",
     "status": "unverified|verified|changed", "source_url": "", "note": "editorial note"}
  ],
  "freshness_note": "Optional – shown under the answer block and in the description.",
  "hashtags": ["#имоти", "#данъци", "#инвестиции"],
  "transcript_file": "transcript.edited.md",
  "article": {
    "slug": "latin-slug-from-title",
    "seo_title": "≤ 60 chars",
    "meta_description": "≤ 155 chars, answer-first",
    "focus_keyphrase": "…",
    "category": "<site.kb_name from brand config>",
    "tags": ["имотни данъци", "…"],
    "embed_caption": "optional caption under the video",
    "date_published": "{{DATE_PUBLISHED}}",
    "related": [{"title": "…", "url": "https://example.com/baza-znaniya/…/"}]
  },
  "facebook": {
    "hook": "1–2 sentences: the direct answer or most concrete fact (the first line must carry the point)",
    "points": ["3–5 short self-contained lines with number and attribution"],
    "question": "optional question that invites comments",
    "hashtags": ["#имоти", "#ипотека"]
  },
  "gates": {"A": "", "youtube": "", "wordpress": "", "facebook": ""}
}
```

Gates: `A` = facts, names, numbers, chapters and title approved (`/yt-aeo:episode`); `youtube`, `wordpress`,
`facebook` = that output's copy (and, for the article, SEO fields and compliance) approved by its own command. A WordPress
draft push needs `gates.wordpress`. Each value is `"<name or 'user'> <ISO date>"`.

Rules the validator enforces (per requested output): ≥ 3 chapters, first at 0, ascending, each ≥ 10 s, no generic
titles; description ≤ 5,000 chars (warns under 100 chars of margin) and no `<`/`>`; article embed is the first block;
FAQ in page = FAQ in schema; every number in answer/takeaways/FAQ/section answers/Facebook copy is found in the
transcript or `claims`.
