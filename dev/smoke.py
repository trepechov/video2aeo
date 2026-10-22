#!/usr/bin/env python3
"""
Smoke checks for the setup flow and the description footer/promo rendering (dev-only, not shipped).
Runs against a temporary VIDEO2AEO_HOME, so it never touches ~/.video2aeo/. Python 3.9+, stdlib only.

  python3 dev/smoke.py          # prints "smoke: N checks ok" or the first failure
  python3 dev/smoke.py --write-article FILE   also copy the rendered test article (for the block validator)
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="video2aeo-smoke-"))
os.environ["VIDEO2AEO_HOME"] = str(TMP / "home")
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "dev"))
import aeo_lib as L  # noqa: E402
import fixture  # noqa: E402

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

# --- legacy ~/.yt-aeo is copied once to ~/.video2aeo (HOME points at a temp dir, no env override) --------
import subprocess
fake_home = TMP / "legacy-home"
(fake_home / ".yt-aeo").mkdir(parents=True)
(fake_home / ".yt-aeo" / "brand.json").write_text('{"channel": "Old"}', encoding="utf-8")
probe = ("import sys; sys.path.insert(0, %r); import aeo_lib as L; "
         "print(L.USER_DIR, L.MIGRATED_FROM, sep='|')" % str(ROOT / "scripts"))
env = {k: v for k, v in os.environ.items() if k not in ("VIDEO2AEO_HOME", "YT_AEO_HOME")}
env["HOME"] = str(fake_home)
out = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, text=True).stdout.strip()
check(out == f"{fake_home / '.video2aeo'}|{fake_home / '.yt-aeo'}", f"legacy folder must be migrated: {out}")
check((fake_home / ".video2aeo" / "brand.json").read_text(encoding="utf-8") == '{"channel": "Old"}'
      and (fake_home / ".yt-aeo" / "brand.json").exists(), "migration must copy and keep the old folder")
out = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, text=True).stdout.strip()
check(out == f"{fake_home / '.video2aeo'}|", f"second run must not migrate again: {out}")

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

# --- episode format: validated, saved, drives the coverage plan -----------------------------------
check(L.save_setup(brand={"format": {"speakers": "choir"}})["ok"] is False, "bad format.speakers rejected")
check(L.save_setup(brand={"format": {"coverage": {"full_until_minutes": 90, "selective_from_minutes": 60}}})["ok"] is False,
      "inverted coverage thresholds rejected")
r = L.save_setup(brand={"format": {"speakers": "host_and_guests", "opening_teaser": "always",
                                   "coverage": {"full_until_minutes": 20, "max_questions_selective": 8}}})
check(r["ok"] and r["current"]["format"]["opening_teaser"] == "always", f"format not saved: {r.get('errors')}")
fmt = r["current"]["format"]
check(fmt["coverage"]["selective_from_minutes"] == 75, "default coverage keys must survive a partial save")
check(L.coverage_plan(15 * 60, fmt)["tier"] == "full", "15 min must be full")
check(L.coverage_plan(40 * 60, fmt)["tier"] == "balanced", "40 min must be balanced")
sel = L.coverage_plan(120 * 60, fmt)
check(sel["tier"] == "selective" and sel["questions"][1] == 8, f"120 min must be selective, max 8: {sel}")
check(L.coverage_plan(0, fmt)["tier"] == "unknown", "unknown length handled")
tb = L.transcript_blocks("# T\n\n<!-- teaser -->\n**[00:01] A:** hook\n<!-- /teaser -->\n\n**[01:00] A:** body\n\n"
                         "<!-- boilerplate -->\n**[59:00] A:** bye\n<!-- /boilerplate -->\n")
check(len(tb) == 1 and "body" in tb[0] and "hook" not in tb[0] and "bye" not in tb[0], "teaser/boilerplate must be dropped")

# --- several formats per brand: profiles override the base ---------------------------------------
check(L.save_setup(brand={"formats": {"clips": {"speakers": "solo"}}})["ok"] is False, "profile without label rejected")
check(L.save_setup(brand={"formats": {"clips": {"label": "Clips", "opening_teaser": "x"}}})["ok"] is False,
      "bad enum in profile rejected")
r = L.save_setup(brand={"formats": {"clips": {"label": "Clips", "speakers": "solo", "coverage": {"full_until_minutes": 15}}}})
check(r["ok"] and "clips" in r["current"]["formats"], f"profile not saved: {r.get('errors')}")
b = L.load_brand()
rf = L.resolve_format(b, "clips")
check(rf["speakers"] == "solo" and rf["opening_teaser"] == "always" and rf["coverage"]["full_until_minutes"] == 15
      and rf["coverage"]["selective_from_minutes"] == 75, f"profile must override only its fields: {rf}")
check(L.resolve_format(b, "nope") == b["format"] and L.resolve_format(b) == b["format"], "unknown profile -> base")
check(L.coverage_plan(18 * 60, rf)["tier"] == "balanced" and L.coverage_plan(18 * 60, b["format"])["tier"] == "full",
      "18 min: balanced for clips (full until 15), full for the base format (until 20)")

check(L.save_setup(brand={"format": {"links": ["javascript:alert(1)"]}})["ok"] is False, "non-http link rejected")
r = L.save_setup(brand={"format": {"notes": "Audience: founders.", "links": ["https://example.org/about"]}})
check(r["ok"] and r["current"]["format"]["links"] == ["https://example.org/about"]
      and r["current"]["format"]["notes"] == "Audience: founders.", f"notes/links not saved: {r.get('errors')}")

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

# --- episodes root, series folders, workspace check, write guard -------------------------------------
root = TMP / "episodes-root"
root.mkdir()
check(L.classify_workspace(root)["status"] == "no_root", "no saved root -> no_root")
wrong = L.check_episode_dir(root / "x" / "y")
check(wrong and wrong.get("episodes_root_missing"), "guard must demand a saved root")
check(L.save_setup(episodes_root="relative/path")["ok"] is False, "relative episodes_root rejected")
check(L.save_setup(episodes_root=str(TMP / "nope"))["ok"] is False, "missing episodes_root folder rejected")
check(L.save_setup(brand={"formats": {"clips": {"label": "Clips", "folder": "Bad Slug"}}})["ok"] is False, "bad folder slug rejected")
check(L.save_setup(brand={"formats": {"clips": {"label": "Clips", "folder": "_other"}}})["ok"] is False, "_other reserved")
cfgp = L.USER_DIR / "config.json"
cfgp.write_text('{"wordpress": {"site": "x"}}', encoding="utf-8")
r = L.save_setup(brand={"formats": {"clips": {"label": "Clips", "folder": "clips"}}}, episodes_root=str(root))
check(r["ok"] and r["current"]["episodes_root"] == str(root.resolve()), f"episodes_root not saved: {r.get('errors')}")
check(L.load_json(cfgp) == {"wordpress": {"site": "x"}, "episodes_root": str(root.resolve())}, "config.json keys must be preserved")
check(r["current"]["series_folders"] == {"clips": "clips"}, f"series_folders: {r['current']['series_folders']}")
check(L.save_setup(brand={"formats": {"talk": {"label": "Talk", "folder": "clips"}}})["ok"] is False, "duplicate series folder rejected")
cfgp.unlink()
L.save_setup(episodes_root=str(root))
cfgp.write_text(json.dumps({"episodes_root": str(root.resolve())}), encoding="utf-8")

b = L.load_brand()
ws = L.classify_workspace(root)
check(ws["ok"] and ws["status"] == "ok", f"cwd = root: {ws}")
(root / "clips").mkdir()
check(L.classify_workspace(root / "clips")["status"] == "ok", "series folder is ok")
check(L.classify_workspace(TMP)["status"] == "ok", "session folder around the root is ok")
link = TMP / "root-link"
link.symlink_to(root, target_is_directory=True)
check(L.classify_workspace(link)["status"] == "ok", "symlink to the root is ok")
other = TMP / "elsewhere"
other.mkdir()
(other.parent / "legacy-ep" / "work").mkdir(parents=True)
(other.parent / "legacy-ep" / "work" / "episode.json").write_text("{}", encoding="utf-8")
sus = L.classify_workspace(Path.home())
check(sus["status"] == "suspicious" and not sus["ok"] and str(root.resolve()) in sus["next_step"], f"home must be suspicious: {sus}")
check(L.classify_workspace(Path.home() / "Downloads")["status"] in ("suspicious", "unknown"), "Downloads not ok")
scratch = TMP / "scratchpad" / "s"
scratch.mkdir(parents=True)
check(L.classify_workspace(scratch)["status"] == "suspicious", "scratchpad must be suspicious")
check(L.classify_workspace(Path("/"))["status"] == "suspicious", "disk root must be suspicious")

p1 = L.episode_path(b, "clips", "20261012", "Нов епизод")
check(p1["ok"] and p1["created"] and p1["episode_dir"].endswith("clips/2026-10-clips-01-nov-epizod"), f"episode_path: {p1}")
check((Path(p1["episode_dir"]) / "work").is_dir(), "work/ must be created")
p1b = L.episode_path(b, "clips", "20261012", "Нов епизод")
check(p1b["episode_dir"] == p1["episode_dir"] and not p1b["created"], "same slug must reuse the folder")
p2 = L.episode_path(b, "clips", "2026-10-20", "second")
check(p2["episode_dir"].endswith("2026-10-clips-02-second"), f"next number: {p2}")
(root / "clips" / "random-folder").mkdir()
check(L.episode_path(b, "clips", None, "third", number=7)["episode_dir"].endswith("-clips-07-third"), "explicit number")
p3 = L.episode_path(b, None, "20261105", "base show")
check(p3["episode_dir"].endswith("_other/2026-11-other-01-base-show"), f"base format goes to _other: {p3}")
check(L.episode_path(b, "clips", None, "!!!")["ok"] is False, "empty slug rejected")
check(L.classify_workspace(p1["episode_dir"])["status"] == "ok", "a fresh episode folder (no episode.json yet) is inside the root")
(Path(p1["episode_dir"]) / "work" / "episode.json").write_text("{}", encoding="utf-8")
ins = L.classify_workspace(p1["episode_dir"])
check(ins["ok"] and ins["status"] == "inside_episode" and ins["episode_dir"] == str(Path(p1["episode_dir"]).resolve()), f"resume: {ins}")

check(L.check_episode_dir(p1["episode_dir"]) is None, "built path passes the guard")
check(L.check_episode_dir(p3["episode_dir"]) is None, "_other path passes the guard")
bad = L.check_episode_dir(TMP / "elsewhere" / "ep")
check(bad and bad["wrong_folder"] and str(root.resolve()) in bad["expected"], f"outside path must fail: {bad}")
check(L.check_episode_dir(root / "ep-directly-in-root")["wrong_folder"], "episode without series folder fails")
check(L.check_episode_dir(root / "unknown-series" / "ep")["wrong_folder"], "unknown series folder fails")
check(L.check_episode_dir(root / "clips" / ".." / ".." / "x")["wrong_folder"], "path traversal fails")
check(L.check_episode_dir(TMP / "legacy-ep") is None, "existing episode outside the root may be resumed")
check(L.check_episode_dir(TMP / "elsewhere" / "ep", allow_outside_root=True) is None, "override passes")

# the MCP layer: wrong folder writes nothing, right folder works
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("v2a_server", ROOT / "server" / "server.py")
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)
before = sorted(p.name for p in TMP.iterdir())
res = srv.call("render_package", {"episode_dir": str(TMP / "elsewhere" / "ep")})
check(res.get("wrong_folder") and sorted(p.name for p in TMP.iterdir()) == before, f"guarded tool must refuse: {res}")
rpc = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": "workspace_status", "arguments": {"cwd": str(Path.home())}}})
check(rpc["result"]["isError"] is False and "suspicious" in rpc["result"]["content"][0]["text"], "workspace_status over JSON-RPC")
names = {t["name"] for t in srv.TOOLS}
check({"workspace_status", "episode_path"} <= names, "new tools listed")
check(all("allow_outside_root" in t["inputSchema"]["properties"] for t in srv.TOOLS if t["name"] in srv.GUARDED),
      "override flag on guarded tools")
res = srv.call("episode_path", {"slug": "via server", "format": "clips", "upload_date": "20261201"})
check(res["ok"] and res["episode_dir"].endswith("-clips-08-via-server"), f"episode_path via server: {res}")

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
import shutil  # noqa: E402
ep_dir = TMP / "ep"
fixture.build(ep_dir)
brand = L.load_brand(ep_dir / "brand.json")
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
check("ADS" in (ep_dir / "youtube-description.txt").read_text(encoding="utf-8"), "promo at end")

# --- fixed header: always first, before a top promo and the answer ---------------------------------
brand["description"].update(header="📢 HEADER LINE", promo="TOPADS", promo_position="top")
L.render_package(ep_dir, brand)
text = (ep_dir / "youtube-description.txt").read_text(encoding="utf-8")
check(text.startswith("📢 HEADER LINE") and text.index("TOPADS") < text.index(brand_answer := L.plain(
    L.load_episode(ep_dir)["answer_short"]).strip()[:40]), "header first, then promo, then answer")
res = L.validate_package(ep_dir, brand)
check(res["ok"] and not any("direct answer" in w for w in res["warnings"]), f"validate with header: {res}")

# --- per-command outputs: the YouTube command works without article content -----------
yt_dir = TMP / "yt-only"
fixture.build(yt_dir)
ep = L.load_json(yt_dir / "work/episode.json")
for key in ("sections", "faq", "key_takeaways"):
    ep.pop(key, None)
(yt_dir / "work/episode.json").write_text(json.dumps(ep, ensure_ascii=False), encoding="utf-8")
r = L.render_package(yt_dir, brand)
check(r["written"] == ["youtube-description.txt"], f"auto outputs must be youtube only: {r}")
check(not (yt_dir / "article.wp.html").exists(), "extra outputs rendered")
res = L.validate_package(yt_dir, brand)
check(res["ok"] and res["outputs_checked"] == ["youtube"], f"youtube-only validate: {res}")
r = L.render_package(yt_dir, brand, ["wordpress"])
check(r["written"] == [] and len(r["skipped"]) == 1, f"incomplete outputs must be skipped, not half-written: {r}")
check(not L.validate_package(yt_dir, brand, ["wordpress"])["ok"], "wordpress validate must fail without sections/faq")
L.write_review(yt_dir, brand, res)
check((yt_dir / "work/review.md").exists() and not (yt_dir / "review.md").exists(), "review.md belongs in work/")
raw = L.write_raw_transcript([{"start": 0.0, "text": "hello"}], yt_dir, "test")
check(all(f.startswith("work/") for f in raw["files"]) and (yt_dir / "work/transcript.raw.txt").exists(),
      "raw transcript must be written to work/")

# --- older flat folders (everything in one folder) are still read ----------------------------------
flat = TMP / "flat"
flat.mkdir()
for f in (ep_dir / "work").iterdir():
    (flat / f.name).write_bytes(f.read_bytes())
check(L.render_package(flat, brand)["written"][0] == "youtube-description.txt", "flat layout not rendered")
check(L.validate_package(flat, brand)["ok"], "flat layout not validated")

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

if "--write-article" in sys.argv:
    out = Path(sys.argv[sys.argv.index("--write-article") + 1])
    out.parent.mkdir(parents=True, exist_ok=True)
    brand["description"].update(promo="", promo_position="end")
    L.render_package(ep_dir, brand, ["wordpress"])
    out.write_bytes((ep_dir / "article.wp.html").read_bytes())

print(f"smoke: {checks} checks ok")
