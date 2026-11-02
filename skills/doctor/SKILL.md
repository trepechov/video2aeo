---
name: doctor
description: >
  This skill should be used when the user runs /video2aeo:doctor, or says that the video2aeo tools do not start, are
  missing, "do not connect", that Python or Git is not found, or that the plugin worked before and stopped. It checks the
  computer without needing the plugin's own helper program and tells the user exactly what to install or fix.
metadata:
  version: "0.8.1"
---

# /video2aeo:doctor – why do the video2aeo tools not start?

Audience: marketers, not developers. Plain language, one short checklist, no jargon. Answer in the user's language.

The plugin's tools (`setup_status`, `check_environment`, …) run in a small helper that needs **Python 3.9 or newer**, and on
Windows **Git for Windows** (it provides the shell the plugin starts everything with). This skill checks both without
using that helper, so it still works when the helper is down.

## 1. Run the check

**Windows first:** run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "${CLAUDE_PLUGIN_ROOT}/server/path-check.ps1")"`.
The Bash tool has its own `sh`, so the check below passes even when the plugin's helper cannot find `sh` – this one
reads the PATH the Claude app really starts with (the registry PATH). Result:
- `on-path` – fine, continue below.
- `found:<folder>` – Git for Windows is installed but the folder is not on the PATH, so the helper cannot start.
  This is the usual case, because the Git installer's default puts only `Git\cmd` on the PATH. Ask the user for
  permission to add that one folder to their own (user) PATH – nothing else is changed – and, on „yes“, run
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "${CLAUDE_PLUGIN_ROOT}/server/fix-path.ps1")" -Folder "<folder>"`.
  Then go to the restart step in section 2.
- `git-missing` – Git for Windows is not installed: section 2.

Run with the Bash tool: `sh "${CLAUDE_PLUGIN_ROOT}/hooks/check-deps.sh"`

- **No output** – a usable Python was found and it is the same as last time. Call `check_environment`; if that tool is
  still missing, the helper did not start for another reason: go to step 3.
- **Output starting with „video2aeo: dependency check FAILED“** – Python is missing or too old: go to step 2.
- **Output saying the Python in use changed** – tell the user which Python is used now and that this can break the tools
  if the new one is older than 3.9 or lives outside the PATH; restarting the Claude app after any Python change fixes it.
- **The Bash tool itself fails or `sh` is not found** (Windows) – Git for Windows is missing or its folder is not on the
  PATH: go to step 2, Git.

## 2. Tell the user what to install (☐ / ✅ checklist, then only the missing steps)

| Needed | Windows | macOS |
|---|---|---|
| Python 3.9+ | python.org/downloads → run the installer → **tick „Add python.exe to PATH“** on the first screen (or install Python from the Microsoft Store) | python.org/downloads → „macOS 64-bit universal2 installer“ (usually already present) |
| Git for Windows | git-scm.com → install with the **default options**; the default leaves `sh` off the PATH, so run this doctor again afterwards – it adds the one folder for you | not needed |

After installing: **close the Claude app completely and open it again** (the PATH is only read at start), switch to
**Claude Code** mode (toggle at the top left), create a **new environment** and choose the working folder, then run
`/video2aeo:doctor` again to confirm.

## 3. If both are installed and the tools are still missing

The app remembers a failed start for about 15 minutes. After fixing something, close the app completely, open it, and
reconnect the server (`/mcp` in Claude Code, or wait for the retry). The video2aeo tools may then show up as deferred
tools: load them with the tool search before the first call.

Ask the user to open the plugin list (Settings → Plugins) and check that **video2aeo** is switched on, and to look at
the message of the failed server (`/mcp` in Claude Code). Common causes: the app was not restarted after installing;
the Windows Store `python.exe` shortcut is in front of the real Python (turn off „App execution aliases“ for python in
Windows Settings or install from the Microsoft Store); a very old Python. Do not edit plugin files by hand.

## 4. Hooks from other plugins

If the user reports that many unrelated tools are blocked (file search, writing files, task lists) with a message
mentioning another script (for example a `*_guard.py`), that comes from another plugin or the user's own settings, not
from video2aeo (it only ships a harmless startup check). Tell the user to run `/hooks`, find the entry that calls
`python3`, and replace `python3` with `python` or `py -3` on Windows, or remove that hook.
