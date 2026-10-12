# Facebook post – structure and rules

Output: `facebook-post.txt` (paste into a Facebook page post). Written by `/video2aeo:fb-post` from `work/episode.json`;
the knowledge comes from the episode's already approved answer, questions and claims – the post adds nothing new.

## Goal

One post that gives a reader the answer in the feed and sends them to the article (and the video). It is a teaser
that is useful on its own, not a copy of the description.

## Structure (rendered from `episode.json → facebook`)

1. `hook` – 1–2 sentences: the direct answer or the most surprising concrete fact of the episode. Facebook cuts long
   posts behind „See more“, so the first line must carry the point (the validator warns above ~150 characters).
2. `points` – 3–5 short bullet lines, each one a self-contained fact or step with its number and attribution.
3. `question` – one question that invites a comment, related to the episode topic (optional but recommended).
4. Links – the article address (from `article.slug`) and the video address, added by the renderer.
5. Brand `facebook.footer` – verbatim, only when the brand set one.
6. `hashtags` – 2–5, at the end.

## Rules

- Language, tone and facts follow the approved description and article: same title wording, same numbers, same
  attribution („според …“) for opinions and forecasts. Every number must be traceable (the validator checks).
- No clickbait the episode does not deliver; no „ШОК“, no ALL CAPS, no emoji walls (a bullet marker or one emoji
  per line at most).
- No promo or investment claims unless they come verbatim from the brand config; never promise returns.
- Pre-2026 лева sums keep the figure and add „(≈ X €)“.
- No sponsor content.
- Do not repeat the whole description: pick the 3–5 points that make someone want the full answer.

## Extending

Add further rules here (posting time, image or video-clip choice, comment-reply policy, group variants …).
Brand-specific additions belong in `~/.video2aeo/guidelines/facebook-post.md`.
