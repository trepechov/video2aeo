#!/usr/bin/env bash
# Prepare a new plugin version: run every check, then bump the version everywhere, then validate again.
# Nothing is changed if a check fails. Usage: dev/release.sh 0.2.1
set -euo pipefail
cd "$(dirname "$0")/.."
new="${1:?usage: dev/release.sh <new-version, e.g. 0.2.1>}"
[[ "$new" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "'$new' is not a x.y.z version"; exit 1; }

echo "== checks"
export YT_AEO_HOME=examples/demo
snapshot() { cat examples/demo/youtube-description.txt examples/demo/article.wp.html examples/demo/facebook-post.txt examples/demo/work/schema.jsonld | shasum; }
before=$(snapshot)
python3 scripts/aeo.py render examples/demo >/dev/null
python3 scripts/aeo.py validate examples/demo | grep -q '"ok": true' || { echo "demo validate failed"; exit 1; }
[ "$before" = "$(snapshot)" ] || { echo "demo output changed on re-render – review and commit it first"; exit 1; }
/usr/bin/python3 scripts/aeo.py validate examples/demo | grep -q '"ok": true' || { echo "Python 3.9 validate failed"; exit 1; }
python3 dev/smoke.py
/usr/bin/python3 dev/smoke.py
if command -v npm >/dev/null; then
  (cd dev && npm i --silent && npm run --silent validate-blocks)
else
  echo "npm not found – WordPress block validator skipped"
fi
if [ -f private/brand-terms.txt ]; then
  if grep -rniIf private/brand-terms.txt --exclude-dir={.git,private,node_modules} --exclude=package-lock.json .; then
    echo "brand terms found in tracked files"; exit 1
  fi
fi

echo "== bump to $new"
python3 - "$new" <<'PY'
import json, re, sys
from pathlib import Path
new = sys.argv[1]
for path in (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"):
    text = Path(path).read_text(encoding="utf-8")
    text, n = re.subn(r'("version":\s*")[^"]+(")', rf"\g<1>{new}\g<2>", text)
    if n != 1:
        sys.exit(f"expected exactly one version in {path}, found {n}")
    json.loads(text)
    Path(path).write_text(text, encoding="utf-8")
for path in Path("skills").glob("*/SKILL.md"):
    text = Path(path).read_text(encoding="utf-8")
    Path(path).write_text(re.sub(r'(?m)^(  version: ")[^"]+(")', rf"\g<1>{new}\g<2>", text), encoding="utf-8")
PY
claude plugin validate .
cat <<EOF

Version is now $new. Next:
  git add -A && git commit -m "yt-aeo $new" && git push
Then in the Claude desktop app: Settings → Plugins → yt-aeo → Update.
EOF
