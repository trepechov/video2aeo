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
