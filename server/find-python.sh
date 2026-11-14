# Shared by server/launch.sh and hooks/check-deps.sh (sourced, POSIX sh, no Python needed).
# find_python sets PY_CMD to the first working Python >= 3.9 among: python3, python, py -3.
# A candidate that only opens the Microsoft Store (the Windows "python.exe" stub) fails the version probe and is skipped.
# macOS: the app may start with a short PATH, so the usual install folders (python.org, Homebrew) are tried as well, and
# /usr/bin/python3 is skipped without the Command Line Tools – it is only a stub that opens an install dialog every time.
find_python() {
  _extra=""
  [ "$(uname -s 2>/dev/null)" = Darwin ] &&
    _extra="/Library/Frameworks/Python.framework/Versions/Current/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3"
  for _cand in "python3" "python" "py -3" $_extra; do
    _exe=$(command -v "${_cand%% *}" 2>/dev/null) || continue
    # The stub check applies on macOS only. On Linux /usr/bin/python3 is the real system Python and xcode-select does not exist.
    if [ "$(uname -s 2>/dev/null)" = Darwin ] && [ "$_exe" = /usr/bin/python3 ] && ! xcode-select -p >/dev/null 2>&1; then continue; fi
    if $_cand -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      PY_CMD=$_cand
      return 0
    fi
  done
  PY_CMD=""
  return 1
}

# Message for a computer without a usable Python. The install steps live in /video2aeo:doctor and the README only.
python_missing_text() {
  cat <<'TXT'
video2aeo needs Python 3.9 or newer, and none was found (on Windows also Git for Windows).
Run /video2aeo:doctor in Claude Code mode (toggle at the top left of the Claude app) for the exact steps, or see the
README's Requirements; then close the Claude app completely and open it again.
TXT
}
