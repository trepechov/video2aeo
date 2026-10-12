# Guideline catalog (shown during setup)

The setup shows this list in plain language. **Locked** rules are enforced by the plugin's code and cannot be
switched off. **Adjustable** rules are the general AEO guidelines; the user may switch each one off. Switched-off ids
go to `guidelines_off` and a "Switched-off guidelines" section in `~/.video2aeo/guidelines.md`, which every skill and
agent reads after the general guidelines.

## Locked (checked by the plugin)

| What | Why |
|---|---|
| YouTube description ≤ 5,000 characters, no `<` or `>` | YouTube rejects it otherwise |
| Chapters: first at 00:00, at least 3, ascending, ≥ 10 s, no generic titles („Интро“, „Финал“) | YouTube only shows chapters then |
| Article starts with the video embed; valid WordPress blocks | Required by the article format |
| Visible FAQ equals the FAQ in the schema | Search engines compare them |
| Every number in the copy is traceable to the transcript or a claim | No invented facts |
| Promo text only from the approved brand config; opinions and forecasts always attributed | Compliance |
| Nothing is published automatically; WordPress push is draft-only after approval | Human stays in control |

## Adjustable (recommended – on by default)

| id | Guideline |
|---|---|
| `answer-first` | The description opens with a 2–3 sentence direct answer, not „В това видео…“ or „Абонирайте се“ |
| `question-titles` | Titles are phrased the way people ask an AI or search; key question in the first ~60 characters; series and episode number at the end |
| `knowledge-chapters` | Chapter titles state the question or knowledge of the segment (the ban on generic titles like „Интро“ stays locked) |
| `question-index` | The description lists 5–6 „Основни въпроси“ and links the article |
| `freshness-note` | Episodes recorded before publishing get a note with the recording date and the date of the data |
| `euro-equivalents` | Pre-2026 лева sums keep the figure and add the euro equivalent in brackets |
| `skip-sponsor-reads` | Sponsor reads are left out of questions, FAQ, claims and the published transcript |
| `question-sections` | The article has one H2 per question, each opening with a 1–2 sentence answer |
| `faq-and-authors` | The article ends with a FAQ (5–8 entries) and an authors box |
