# YouTube description – structure and rules

Output: `youtube-description.txt` (paste into YouTube Studio → Details → Description). Written by `/yt-aeo:episode`.
The text lives in `work/episode.json`; `render_package` assembles it in the fixed order below – never hand-edit the file.

## Goal

The description is the page of text YouTube and AI systems read *about* the video. It must stand alone as the start
of an article: a direct answer, the questions the episode answers, and chapters that name the knowledge in each segment.
The brand footer (promo, disclaimer, socials) is necessary but is not the content – it sits at the end.

## Fixed order

0. Brand `description.header` – verbatim, only if the brand set one. Never write or reword it.
   (The promo block goes here instead, at the very top, when `description.promo_position` is `top`.)
1. `answer_short` – 2–3 sentences that directly answer the episode's main question. Makes sense without the video,
   names its subject, keeps the key number with its date and speaker. Never „В това видео говорим за…“, never „Абонирайте се“.
2. `context` – 1–2 sentences: series, host, guest with role, what is covered.
3. „Основни въпроси, на които ще получите отговор:“ – `questions[].q`, 5–6 bullets, phrased the way people ask an AI.
4. Article link – built from `article.slug` and the brand site config. The article may not exist yet; the link is
   the address it will get.
5. „⏱️ Глави:“ – `chapters`.
6. `freshness_note`, if any.
7. Host / guest line – from `people`.
8. Brand footer – schedule, disclaimer + link, socials, and the approved promo (at `{PROMO}`). Never write promo text yourself.
9. Up to 3 `hashtags` (YouTube shows the first three above the title).

Why this order: the first lines are what search results, the collapsed description and AI answers quote – so the
answer comes first; questions and chapters give the topic map; the footer is last because it is identical in every episode.

## Chapters

- First chapter `t: 0`; at least 3; strictly ascending; each ≥ 10 s; one per distinct question; roughly 1 per 2–4
  minutes (a 50-minute episode: 12–22).
- Title = the question or the knowledge the segment gives: „Защо рекордните депозити не са добра новина“, not „Депозити“.
  Never generic: Интро, Разговор, Пазар, Съвети, Финал, Заключение.
- ≤ 70 characters (the first 49 show on hover); sentence case, no emoji, no trailing period.
- Do not start a chapter inside a sponsor read; let the previous chapter cover it.
- Timestamps come from the transcript stamps, rounded down to the start of the sentence that opens the topic.

## Title (shared with the article and the Facebook post)

Offer three options at Gate A: (1) the main question, (2) a statement or list, (3) the expert framing with the guest.
Phrase it the way people ask an AI or search; key question in the first ~60 characters, series name and episode
number at the end: „… | <series> Еп. 8“. No ALL CAPS, no „ШОК“, no clickbait the episode does not deliver.
The chosen title is both the YouTube title and the WordPress article title.

## Limits (enforced by the code)

- ≤ 5,000 characters once placeholders are filled; keep ≥ 100 characters of margin.
- No `<` or `>` (YouTube rejects them – the renderer replaces them).
- Over the limit: shorten `context`, cut questions to 5, merge adjacent short chapters, then ask the brand owner to
  shorten the footer (move the full disclaimer to the website and link it).

## Writing rules

- Opinions and forecasts are attributed („според …“); numbers keep their date and speaker.
- Pre-2026 лева sums keep the figure and add „(≈ X €)“ at 1,95583.
- Sponsor reads are not knowledge: no sponsor content in the answer, questions or chapters.
- Promo and investment claims only from the approved brand config.

## Extending

Add further rules here (hashtag policy, pinned-comment text, end-screen wording …). Brand-specific additions belong
in `~/.yt-aeo/guidelines/youtube-description.md`.

See `skills/episode/references/example-youtube-description.txt` for a complete rendered example (fictional demo brand).
