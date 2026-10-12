#!/usr/bin/env bash
# Build an installable plugin zip (for Claude desktop → Customize → Plugins → Upload).
# Leaves out repo-only material: docs, dev tooling, git, Claude Code project settings.
set -euo pipefail
cd "$(dirname "$0")/.."
ver=$(python3 -c "import json;print(json.load(open('.claude-plugin/plugin.json'))['version'])")
out="dist/yt-aeo-$ver.plugin"
mkdir -p dist && rm -f "$out"
zip -qr "$out" . -x ".git/*" ".claude/*" "docs/*" "dev/*" "dist/*" "episodes/*" "evals/*" "private/*" "examples/*" "*__pycache__*" "*.DS_Store" ".gitignore"
echo "$out"
