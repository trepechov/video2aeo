#!/bin/sh
# SessionStart check: is a usable Python available, and (Windows) can the Claude app find `sh` to start the helper?
# Needs no Python itself, writes nothing, and ALWAYS exits 0 so it can never block a session.
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
    sh_dir=$(cygpath -w "$(dirname "$(command -v sh)")" 2>/dev/null) || sh_dir=""
    set --
    [ -n "$sh_dir" ] && set -- -ShFolder "$sh_dir"   # the running sh: finds Git in any folder (Scoop, portable)
    if [ -n "$ps1" ] && command -v powershell.exe >/dev/null 2>&1; then
      state=$(powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$ps1" "$@" 2>/dev/null | tr -d '\r')
      case "$state" in
        found:*)
          echo "video2aeo: dependency check FAILED. The Windows PATH of the Claude app has no 'sh' (from Git for Windows), so the video2aeo helper cannot start."
          echo "Tell the user in plain words and run /video2aeo:doctor, which adds the folder below with the user's OK. Restart of the Claude app is needed afterwards."
          printf 'video2aeo-path-fix: %s\n' "${state#found:}"   # printf: echo may eat the backslashes of C:\...
          exit 0;;
        git-missing)
          echo "video2aeo: dependency check FAILED. Git for Windows (it provides 'sh') was not found, so the video2aeo helper cannot start."
          echo "Tell the user in plain words and run /video2aeo:doctor for the install steps."
          exit 0;;
      esac
    fi;;
esac
exit 0
