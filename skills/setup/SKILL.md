---
name: setup
description: >
  This skill should be used when the user asks to "set up the AEO plugin", "install the subtitle downloader",
  "connect WordPress", "configure yt-aeo", or when fetch_transcript / wp_push_draft report a missing dependency or
  missing credentials. It guides the one-time setup on the marketer's computer.
metadata:
  version: "0.1.0"
---

# One-time setup for the AEO Episode Agent

Guide the user in plain language, one step at a time. Check each step before moving on.

## 1. Run in Cowork on the computer

The subtitle downloader and WordPress push run on the user's own computer (YouTube blocks cloud servers). Ask the
user to start the work as a Cowork task in the Claude desktop app with a working folder selected (e.g.
`Documents/YT-AEO`). In plain chat the plugin still works, but the user must paste or attach the transcript.

## 2. Python 3

The tools need `python3` (preinstalled on most Macs; on Windows install from python.org and tick "Add to PATH").
Test: ask the user to open Terminal and run `python3 --version` – 3.9 or newer is fine.
On Windows, if `python3` is not found but `python` is, tell the admin to change `"command"` in the plugin's
`.mcp.json` to `python`.

## 3. Subtitle downloader

In Terminal: `python3 -m pip install --user youtube-transcript-api` (on macOS with Homebrew Python add
`--break-system-packages` if pip refuses). Optional second route: `brew install yt-dlp`.
Then restart the Claude desktop app so the tools reload. Test with `get_video_info` on any channel video.

## 4. WordPress (optional – only to push drafts)

1. In WordPress: Users → Profile → **Application Passwords** → name „Claude AEO“ → Add → copy the password.
   Use an Editor (not Administrator) account if the Custom HTML schema block is not needed; otherwise Administrator.
2. Create the file `~/.yt-aeo/config.json` (in the user's home folder) with:
   ```json
   {"wordpress": {"base_url": "https://your-site.example", "username": "<wp user>", "app_password": "xxxx xxxx xxxx xxxx xxxx xxxx"}}
   ```
   Never put the password in chat, in the plugin, or in the episode folder.
3. Make sure the knowledge-base category (`site.kb_name` in the brand config) exists (the tool does not create categories).

## 5. Brand and glossary (required before the first real episode)

The plugin ships generic defaults only. The brand lives on the user's computer:
- `~/.yt-aeo/brand.json` – any keys of the plugin's `config/brand.json` (channel, series, topics, site, organization,
  people, approved footer with the promo block, disclaimer). It is merged over the defaults.
- `~/.yt-aeo/glossary.json` – brand names, people, ASR fixes and sponsor-read markers (same keys as `config/glossary.json`).

- `~/.yt-aeo/guidelines.md` (optional, or several files in `~/.yt-aeo/guidelines/`) – brand-specific instructions
  in plain Markdown: tone, terminology, compliance rules, house style. They extend the plugin's general AEO
  guidelines.

Get these files from the brand owner (the team keeps them outside the plugin repo). Fill every `{{…}}` value –
the validator lists any that remain.
