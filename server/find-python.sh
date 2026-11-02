# Shared by server/launch.sh and hooks/check-deps.sh (sourced, POSIX sh, no Python needed).
# find_python sets PY_CMD to the first working Python >= 3.9 among: python3, python, py -3.
# A candidate that only opens the Microsoft Store (the Windows "python.exe" stub) fails the version probe and is skipped.
find_python() {
  for _cand in "python3" "python" "py -3"; do
    command -v "${_cand%% *}" >/dev/null 2>&1 || continue
    if $_cand -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      PY_CMD=$_cand
      return 0
    fi
  done
  PY_CMD=""
  return 1
}

# Message for a computer without a usable Python (shared wording, plain language).
python_missing_text() {
  cat <<'TXT'
video2aeo needs Python 3.9 or newer, and none was found.
  Windows: install it from python.org/downloads and tick "Add python.exe to PATH" (or install Python from the
           Microsoft Store), install Git for Windows with the default options (git-scm.com), then restart the Claude app.
  macOS:   install the "macOS 64-bit universal2 installer" from python.org/downloads, then restart the Claude app.
Then work in Claude Code mode (toggle at the top left of the Claude app).
TXT
}
