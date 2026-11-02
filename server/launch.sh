#!/bin/sh
# Starts the video2aeo MCP server with whichever Python the computer has (python3, python or py -3).
# Run as `sh launch.sh` from .mcp.json, so it works on macOS, Linux and Windows (Git for Windows provides sh).
self=$(printf '%s' "$0" | tr '\\' '/')   # Windows passes C:\...\launch.sh
here=$(cd "$(dirname "$self")" && pwd)
. "$here/find-python.sh"
if find_python; then
  exec $PY_CMD "$here/server.py" "$@"
fi
python_missing_text >&2
exit 1
