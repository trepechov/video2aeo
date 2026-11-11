---
name: doctor
description: >
  This skill should be used when the user runs /video2aeo:doctor, or says that the video2aeo tools do not start, are
  missing, "do not connect", that Python or Git is not found, or that the plugin worked before and stopped. It checks the
  computer without needing the plugin's own helper program and tells the user exactly what to install or fix.
metadata:
  version: "0.10.0"
---

# /video2aeo:doctor – why do the video2aeo tools not start?

Audience: marketers, not developers. Plain language, one short checklist, no jargon. Answer in the user's language.

The plugin's tools (`setup_status`, `check_environment`, …) run in a small helper that needs **Python 3.9 or newer**, and on
Windows **Git for Windows** (it provides the shell the plugin starts everything with). This skill checks both without
using that helper, so it still works when the helper is down.

## 0. Is this Claude Code mode?

If you have no Bash/shell tool, or `${CLAUDE_PLUGIN_ROOT}` is empty, the user is in plain chat: skills load there but the
helper, hooks and agents do not. Tell them to switch the Claude desktop app to **Claude Code** mode (toggle at the top
left), create a **new environment**, choose the working folder and run `/video2aeo:doctor` again – and stop here. Do
not diagnose Python or Git in this case.

## 1. Run the check

Run with the Bash tool: `sh "${CLAUDE_PLUGIN_ROOT}/hooks/check-deps.sh"`. It needs no Python and, on Windows, also reads
the PATH the Claude app really starts with (the registry PATH – the Bash tool's own `sh` says nothing about it).

- **No output** – Python is fine and, on Windows, the app can find `sh`. Call `check_environment` (it reports the
  Python the helper really runs, `python.executable`); if that tool is still missing, go to step 3.
- **A line `video2aeo-path-fix: <folder>`** (Windows) – Git for Windows is installed but its folder is not on the PATH,
  so the helper cannot start. This is the usual case: the Git installer's default puts only `Git\cmd` on the PATH. Show
  the user that exact folder and ask for permission to add it to their own (user) PATH – nothing else is changed. On
  „yes“ run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "${CLAUDE_PLUGIN_ROOT}/server/path-check.ps1")" -Fix -Folder "<folder>"`
  (`added:` or `already-present` – done; `error:` – tell the user and go to step 2, Git). Then the restart in step 2.
- **Any other output starting with „video2aeo: dependency check FAILED“** – Python, or on Windows Git for Windows, is
  missing or too old: step 2.
- **The Bash tool itself fails** (Windows) – run the PATH check with PowerShell directly instead:
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<plugin folder>\server\path-check.ps1"`, where the plugin
  folder is two levels above this skill's base directory (shown when the skill loaded). `found:<folder>`
  is handled like the `video2aeo-path-fix` line above, `git-missing` and errors go to step 2.

## 2. Tell the user what to install (☐ / ✅ checklist, then only the missing steps)

This table is the one place with the install steps; setup, the README and the start-up messages point here.

| Needed | Windows | macOS |
|---|---|---|
| Python 3.9+ | python.org/downloads → run the installer → **tick „Add python.exe to PATH“** on the first screen (or install Python from the Microsoft Store) | python.org/downloads → „macOS 64-bit universal2 installer“ (or, in Terminal, `xcode-select --install`, which also brings Python 3.9) |
| Git for Windows | git-scm.com → install with the **default options**; the default leaves `sh` off the PATH, so run this doctor again afterwards – it adds the one folder for you | not needed |

After installing or fixing the PATH: **close the Claude app completely** (also from the tray / menu bar) **and open it
again** – the PATH is only read at start, and the app remembers a failed helper start for about 15 minutes. Switch to
**Claude Code** mode (toggle at the top left), create a **new environment**, choose the working folder and run
`/video2aeo:doctor` again to confirm. Then go back to what the user was doing (or `/video2aeo:resume`).

## 3. If everything is installed and the tools are still missing

Reconnect the server (`/mcp` in Claude Code, or wait for the retry); the video2aeo tools may then show up as deferred
tools – load them with the tool search before the first call. Ask the user to check in Settings → Plugins that
**video2aeo** is switched on, and to look at the message of the failed server (`/mcp`). Common causes: the app was not
fully restarted; the Windows Store `python.exe` shortcut is in front of the real Python (turn off „App execution
aliases“ for python in Windows Settings); a very old Python. Do not edit plugin files by hand.

If many unrelated tools are blocked with a message naming another script (for example a `*_guard.py`), that is a hook of
another plugin or of the user's settings, not video2aeo: the user can find and fix or remove it with `/hooks`.
