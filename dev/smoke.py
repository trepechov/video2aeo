#!/usr/bin/env python3
"""
Smoke checks for the setup flow and the description footer/promo rendering (dev-only, not shipped).
Runs against a temporary YT_AEO_HOME, so it never touches ~/.yt-aeo/. Python 3.9+, stdlib only.

  python3 dev/smoke.py          # prints "smoke: N checks ok" or the first failure
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="yt-aeo-smoke-"))
os.environ["YT_AEO_HOME"] = str(TMP / "home")
sys.path.insert(0, str(ROOT / "scripts"))
import aeo_lib as L  # noqa: E402

checks = 0


def check(cond, msg):
    global checks
    if not cond:
        sys.exit(f"smoke FAILED: {msg}")
    checks += 1


def desc(**overrides):
    d = json.loads(json.dumps(L.load_json(ROOT / "config" / "brand.json")["description"]))
    d.update(schedule="every Wednesday", disclaimer_url="https://example.org/d", social_links="links")
    d.update(overrides)
    return d


# --- guideline catalog and code agree -----------------------------------------------------------
catalog = (ROOT / "skills/setup/references/guideline-catalog.md").read_text(encoding="utf-8")
ids = re.findall(r"^\| `([a-z-]+)` \|", catalog, re.M)
check(tuple(ids) == L.ADJUSTABLE_GUIDELINES, f"catalog ids {ids} != ADJUSTABLE_GUIDELINES")

# --- environment check is read-only --------------------------------------------------------------
env = L.check_environment()
check(env["ok"] and env["python"]["ok"], f"check_environment not ok: {env['problems']}")
check(not L.USER_DIR.exists(), "check_environment must not create the settings folder")

# --- first run: not configured, nothing written ---------------------------------------------------
st = L.setup_status()
check(not st["configured"] and not st["setup_completed"], "fresh folder must not be configured")
check(st["required_missing"] == ["channel", "topics"], f"required_missing: {st['required_missing']}")
check(L.save_setup()["ok"] is False, "empty save_setup must fail")
check(not L.USER_DIR.exists(), "failed save_setup must not write")
bad = L.save_setup(brand={"channel": "X"}, guidelines_off=["number-traceability"])
check(bad["ok"] is False and "Unknown or locked" in bad["errors"][0], "locked/unknown guideline id must be rejected")
check(L.save_setup(brand={"description": {"promo_position": "middle"}})["ok"] is False, "bad promo_position rejected")

# --- skipping optional fields still reaches configured; dotted keys are expanded ------------------
r = L.save_setup(brand={"channel": "Demo", "topics": "money", "description.promo": "PROMO TEXT"},
                 guidelines_md="# House\n", guidelines_off=["euro-equivalents"])
check(r["ok"] and r["configured"], f"setup with skipped optional fields must be configured: {r.get('missing')}")
saved = L.load_json(L.USER_DIR / "brand.json")
check(saved["description"]["promo"] == "PROMO TEXT" and "description.promo" not in saved, "dotted key not expanded")
check(saved["organization"]["logo"] == "" and saved["description"]["schedule"] == "", "optional fields not blanked")

# --- partial re-run keeps earlier answers; guidelines.md is backed up ------------------------------
r = L.save_setup(brand={"channel": "Demo 2"})
check(r["guidelines_off"] == ["euro-equivalents"], "guidelines_off must survive a save without it")
check(L.load_json(L.USER_DIR / "brand.json")["description"]["promo"] == "PROMO TEXT", "promo lost on re-run")
L.save_setup(guidelines_md="# House v2\n")
check((L.USER_DIR / "guidelines.md.bak").read_text(encoding="utf-8") == "# House\n", "guidelines.md not backed up")
check(L.setup_status()["current"]["guidelines_md"] == "# House v2\n", "status must return current guidelines")

# --- damaged files: status reports, save repairs ----------------------------------------------------
(L.USER_DIR / "setup.json").write_text('{"compl', encoding="utf-8")
st = L.setup_status()
check(not st["configured"] and st["unreadable"], "corrupt setup.json must be reported, not raised")
(L.USER_DIR / "brand.json").write_text("not json", encoding="utf-8")
check(L.setup_status()["unreadable"], "corrupt brand.json must be reported")
r = L.save_setup(brand={"channel": "Demo", "topics": "money"})
check(r["ok"] and r["configured"] and "brand.json.broken" in r["set_aside"], f"save must repair: {r}")

# --- footer / promo rendering ---------------------------------------------------------------------
top, foot = L._promo_and_footer(desc())
check(top == "" and "{PROMO}" not in foot and "\n\n" not in foot, "empty promo must collapse separators")
check("every Wednesday" in foot and "https://example.org/d" in foot, "footer tokens not filled")
top, foot = L._promo_and_footer(desc(promo="ADS", social_links=""))
check(top == "" and "ADS" in foot and "📲" not in foot, "promo at end / empty social line dropped")
top, foot = L._promo_and_footer(desc(promo="ADS", promo_position="top"))
check(top == "ADS" and "ADS" not in foot, "promo at top")
legacy = desc(footer="Line\n____________\nOLD ADS\n____________\nEnd", promo="OLD ADS")
check(L._promo_and_footer(legacy)[1].count("OLD ADS") == 1, "legacy footer with the same promo must not duplicate")
alias = desc(footer="A\n____________\n{{PROMO_BLOCK}}\n____________\nB", promo="ADS")
check("ADS" in L._promo_and_footer(alias)[1] and "{{" not in L._promo_and_footer(alias)[1], "{{PROMO_BLOCK}} alias")
check("{{SCHEDULE}}" in L._promo_and_footer(desc(footer="x {{SCHEDULE}}"))[1], "literal {{X}} must stay visible")

# --- validator with the promo at the top (incl. a promo that contains a separator) ------------------
ep_dir = TMP / "ep"
ep_dir.mkdir()
for f in (ROOT / "examples/demo").iterdir():
    if f.is_file():
        (ep_dir / f.name).write_bytes(f.read_bytes())
brand = L.load_brand(ROOT / "examples/demo/brand.json")
for promo in ("👉 Offer: https://example.org/a", f"Line 1\n{L.DESC_SEP}\nLine 2"):
    brand["description"].update(promo=promo, promo_position="top")
    L.render_package(ep_dir, brand)
    text = (ep_dir / "youtube-description.txt").read_text(encoding="utf-8")
    check(text.startswith(promo), "top promo not rendered first")
    res = L.validate_package(ep_dir, brand)
    check(res["ok"], f"validate with top promo: {res['errors']}")
    check(not any("direct answer" in w for w in res["warnings"]), f"answer check confused by promo: {res['warnings']}")
brand["description"].update(promo="ADS", promo_position="end")
L.render_package(ep_dir, brand)
check("ADS" in (ep_dir / "youtube-description.txt").read_text(encoding="utf-8"), "promo at end (demo footer)")

# --- fixed header: always first, before a top promo and the answer ---------------------------------
brand["description"].update(header="📢 HEADER LINE", promo="TOPADS", promo_position="top")
L.render_package(ep_dir, brand)
text = (ep_dir / "youtube-description.txt").read_text(encoding="utf-8")
check(text.startswith("📢 HEADER LINE") and text.index("TOPADS") < text.index(brand_answer := L.plain(
    L.load_json(ep_dir / "episode.json")["answer_short"]).strip()[:40]), "header first, then promo, then answer")
res = L.validate_package(ep_dir, brand)
check(res["ok"] and not any("direct answer" in w for w in res["warnings"]), f"validate with header: {res}")

# --- empty brand glossary is reported ---------------------------------------------------------------
check(any("glossary" in w for w in L.setup_status()["warnings"]) or L.setup_status()["glossary_entries"] > 0,
      "empty glossary must warn")

# --- optional yt-dlp cookies from config.json --------------------------------------------------------
import aeo_net as N  # noqa: E402
cfgp = L.USER_DIR / "config.json"
cfgp.parent.mkdir(parents=True, exist_ok=True)
cfgp.write_text('{"youtube": {"cookies_from_browser": "chrome"}}', encoding="utf-8")
check(N._yt_cookie_args() == ["--cookies-from-browser", "chrome"], "cookies_from_browser not passed")
cfgp.write_text('{"youtube": {"cookies_file": "/x/c.txt", "cookies_from_browser": "chrome"}}', encoding="utf-8")
check(N._yt_cookie_args() == ["--cookies", "/x/c.txt"], "cookies_file must win")
cfgp.write_text('{"wordpress": {}}', encoding="utf-8")
check(N._yt_cookie_args() == [], "no youtube config -> no cookie args")
cfgp.unlink()

print(f"smoke: {checks} checks ok")
