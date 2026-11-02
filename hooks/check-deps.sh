#!/bin/sh
# SessionStart check: is a usable Python available, and did its location change since the last session?
# Needs no Python itself, is read-only apart from one small note file, and ALWAYS exits 0 so it can never block a session.
self=$(printf '%s' "$0" | tr '\\' '/')
here=$(cd "$(dirname "$self")/../server" && pwd) || exit 0
. "$here/find-python.sh" || exit 0

if ! find_python; then
  echo "video2aeo: dependency check FAILED."
  python_missing_text
  echo "Tell the user this in plain words and point them to /video2aeo:doctor. The video2aeo tools will not work until Python is installed."
  exit 0
fi

# Windows: the app starts the helper with `sh`; the PATH it sees is the registry PATH, not this shell's. Fail open.
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*)
    ps1=$(cygpath -w "$here/path-check.ps1" 2>/dev/null) || ps1=""
    if [ -n "$ps1" ] && command -v powershell.exe >/dev/null 2>&1; then
      state=$(powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$ps1" 2>/dev/null | tr -d '\r')
      case "$state" in
        found:*|git-missing)
          echo "video2aeo: dependency check FAILED. The Windows PATH of the Claude app has no 'sh' (from Git for Windows), so the video2aeo helper cannot start."
          echo "Tell the user in plain words and run /video2aeo:doctor, which can fix it in one step. Restart of the Claude app is needed afterwards."
          exit 0;;
      esac
    fi;;
esac

exe=$($PY_CMD -c 'import sys; print(sys.executable)' 2>/dev/null)
home=${VIDEO2AEO_HOME:-$HOME/.video2aeo}
note="$home/last_python"
if [ -d "$home" ]; then
  last=$(cat "$note" 2>/dev/null)
  if [ -n "$last" ] && [ "$last" != "$exe" ]; then
    echo "video2aeo: the Python in use changed (was $last, now $exe). If the video2aeo tools fail, run /video2aeo:doctor."
  fi
  printf '%s\n' "$exe" > "$note" 2>/dev/null
fi
exit 0
