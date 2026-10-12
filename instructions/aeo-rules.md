# AEO rules (condensed from the brand's AEO handbook)

Adjustable rules carry an id in brackets, e.g. `[answer-first]` (list: `skills/setup/references/guideline-catalog.md`).
A rule whose id is listed under "Switched-off guidelines" in `~/.video2aeo/guidelines.md` is not applied. Rules without
an id are enforced by the plugin's code and cannot be switched off.

AI systems do not watch video. They extract and cite **text connected to it**: title, description, transcript,
chapters, the page the video is embedded in, and other pages on the topic. No text → the conversation does not exist
for an LLM, however good it is.

## The five pillars

| Pillar | What must exist | Test before publishing |
|---|---|---|
| 1. Transcript | Full, **edited** (not auto) transcript | Can a single sentence be quoted on its own? |
| 2. Chapters | Knowledge-based title for every segment | From the title alone, is it clear which problem is solved? |
| 3. Title & description | Natural question/statement + direct answer in the first 2 sentences | Does it read like the start of an article, not a YouTube hook? |
| 4. Article + schema | Knowledge-base page with the video, text, FAQ, author, VideoObject | Is the page richer than the video alone? |
| 5. Format | how-to / comparison / demonstration / expert interview | Can you say in one sentence what knowledge AI will extract? |

## Writing citable sentences

- Weak (auto): „ами тука нали общо взето значи ако така погледнем…“
- Strong (edited): „Новият навик се затвърждава средно за 66 дни, а не за 21, както често се твърди.“
- Each key sentence names its subject (no „това“, „той“ without an antecedent) and keeps its number + date.

## Chapters

Weak: `00:00 Начало / 07:20 Навици / 18:10 Мотивация / 31:00 Заключение`
[knowledge-chapters] Strong: `00:00 Колко време отнема да изградим навик / 07:20 Защо мотивацията не стига / …`
Never: Интро, Разговор, Пазар, Съвети, Финал. One chapter per distinct question, ~1 per 2–4 min.
YouTube rules: first at 00:00, ≥ 3 chapters, ascending, each ≥ 10 s; titles ≤ 70 chars (≤ 49 show on hover).

## Titles

- Video answers one question → use the question („Струва ли си да учим програмиране след 40?“).
- List / analysis / framework → clear statement („3 признака, че е време да смените работата си“).
- [question-titles] Rule: phrase it the way people **ask an AI or search**. Keep the key question in the first ~60 characters;
  series name and episode number go at the end („… | <series> Еп. 8“).
- Interviews: the expert answer is the asset – „Как работодателите оценяват кандидат без опит? Разговор с HR директор“,
  not „Подкаст с Иван Иванов“.

## Description

[answer-first] First 2–3 sentences = direct answer (start of an article). Then context (who/what), then
[question-index] „Основни въпроси, на които ще получите отговор:“ with 5–6 bullets, then article link, chapters, people, footer.
Never open with „В това видео говорим за…“ or „Абонирайте се“.

## Article

1 recording = 1 knowledge hub. Video first, short answer block, takeaways, chapter links, [question-sections] one H2 per question
(each opening with a 1–2 sentence answer), tables for comparisons, [faq-and-authors] visible FAQ = FAQPage schema, edited transcript,
authors, related answers, disclaimer. Lives in the knowledge base (`site.kb_name`), not the blog.

## Freshness and facts

- Every number keeps its date and speaker. Opinions: „според Мария Георгиева…“. Forecasts are framed as forecasts.
- [euro-equivalents] Bulgaria uses the euro since 1 Jan 2026: pre-2026 лева sums keep the figure and add „(≈ X €)“ at 1,95583.
- [freshness-note] Recorded-before-publishing episodes get a freshness note („Епизодът е записан през … г.; данните са към …“).
- [skip-sponsor-reads] Sponsor reads are not knowledge: skip them in questions, FAQ, claims and the published transcript.

## The planning test

YouTube asks: will people watch this? An LLM asks: can I use this as a source?
Every episode answers some of the questions the channel wants to own – name them in `questions[]`.
