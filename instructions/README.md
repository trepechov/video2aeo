# Instructions – one file per output

These files are the plugin's general instructions for each thing it produces. The commands read them, in this order:

1. `aeo-rules.md` – the AEO principles every output follows (five pillars, citable sentences, attribution, freshness).
2. The file of the output being written:

| Output (file in the episode folder) | Command | Instruction file |
|---|---|---|
| `youtube-description.txt` (+ title, chapters) | `/yt-aeo:episode` | `youtube-description.md` |
| `article.wp.html`, `wp-post-fields.json` | `/yt-aeo:wp-article` | `wordpress-article.md` |
| `facebook-post.txt` | `/yt-aeo:fb-post` | `facebook-post.md` |

3. The brand's own instructions on the user's computer, which extend or override the general ones – but never the rules
   the code enforces: `~/.yt-aeo/guidelines.md`, then every `~/.yt-aeo/guidelines/*.md`. A file in that folder named
   like an instruction file here (`wordpress-article.md`, `facebook-post.md`, `youtube-description.md`) is read for that
   output.

`episode-schema.md` describes `work/episode.json`, the single source of truth every output is rendered from.

New output (Instagram, newsletter …) = one new instruction file here, one skill, one block in `episode.json`, one
renderer in `scripts/aeo_lib.py`.
