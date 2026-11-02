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

# --- long episodes: chunked editing survives a crash, state comes from the files -----------------------
import aeo_pipeline as P  # noqa: E402


def raw_para(sec, n=40):
    return f"[{L.fmt_ts(sec)}] " + " ".join(f"дума{sec}x{i}" for i in range(n))


def fake_edit(ep, n, header=False, sponsor_first=False, sponsor_last=False):
    cd = ep / "work" / "chunks"
    paras = [t for _, t in P._paragraphs((cd / f"{n:02d}.raw.txt").read_text(encoding="utf-8"))]
    out = ["# Транскрипт – Тест\n\nВодещ: Иван\n"] if header else []
    for i, t in enumerate(paras):
        m = re.match(r"\[([\d:]+)\] (.*)", t, re.S)
        line = f"**[{m.group(1)}] Иван:** {m.group(2)}"
        if (sponsor_first and i == 0) or (sponsor_last and i == len(paras) - 1):
            line = f"<!-- sponsor -->\n{line}\n<!-- /sponsor -->"
        out.append(line)
    (cd / f"{n:02d}.edited.md").write_text("\n\n".join(out) + "\n", encoding="utf-8")


long_ep = TMP / "long"
(long_ep / "work").mkdir(parents=True)
raw_path = long_ep / "work" / "transcript.raw.txt"
raw_path.write_text("\n\n".join(raw_para(s) for s in range(0, 40 * 60, 30)) + "\n", encoding="utf-8")
st = P.episode_status(long_ep)
check(st["step"] == "edit_transcript" and "split_transcript" in st["next_action"], f"not split yet: {st['step']} {st['next_action']}")
sp = P.split_transcript(long_ep)
check(sp["ok"] and sp["total"] == 4 and sp["todo"] == [1, 2, 3, 4], f"40 min -> 4 chunks of 10 min: {sp}")
check((long_ep / "work/chunks/02.context.txt").exists() and not (long_ep / "work/chunks/01.context.txt").exists(), "context files")
check(P.split_transcript(long_ep)["reused"] is True, "same transcript must reuse the split")
fake_edit(long_ep, 1, header=True, sponsor_last=True)
fake_edit(long_ep, 2, sponsor_first=True)
st = P.episode_status(long_ep)
check(st["chunks"]["done"] == 2 and "3-4" in st["next_action"], f"two chunks done: {st['next_action']}")
# crash while writing chunk 3: a truncated file must not count as done
f3 = long_ep / "work/chunks/03.edited.md"
fake_edit(long_ep, 3)
f3.write_text(f3.read_text(encoding="utf-8")[:1500], encoding="utf-8")
st = P.episode_status(long_ep)
check(st["chunks"]["invalid"] and st["chunks"]["invalid"][0]["n"] == 3 and "3-4" in st["next_action"], f"truncated chunk: {st}")
mg = P.merge_transcript(long_ep)
check(not mg["ok"] and mg["invalid"][0]["n"] == 3 and mg["todo"] == [4], f"merge must refuse: {mg}")
fake_edit(long_ep, 3)
fake_edit(long_ep, 4)
check(P.episode_status(long_ep)["next_action"] == "merge_transcript", "all chunks done -> merge")
mg = P.merge_transcript(long_ep)
check(mg["ok"], f"merge: {mg}")
merged = (long_ep / "work/transcript.edited.md").read_text(encoding="utf-8")
check(merged.count("# Транскрипт") == 1 and merged.count("<!-- sponsor -->") == 1 and merged.count("<!-- /sponsor -->") == 1,
      "title once; a sponsor block across a chunk border becomes one block")
check(P.episode_status(long_ep)["step"] == "knowledge_map", "after merge the next step is the knowledge map")
# the episode was extended: re-split keeps the edited chunks whose text did not change
raw_path.write_text(raw_path.read_text(encoding="utf-8") + "\n" + raw_para(40 * 60) + "\n\n" + raw_para(40 * 60 + 400) + "\n", encoding="utf-8")
st = P.episode_status(long_ep)
check(st["stale"] and "split_transcript" in st["next_action"], f"stale after the raw transcript changed: {st}")
check(not P.merge_transcript(long_ep)["ok"], "merge must refuse a stale split")
sp = P.split_transcript(long_ep)
check(sp["kept_edited"] == [1, 2, 3, 4] and sp["todo"] == [5], f"re-split keeps finished chunks: {sp}")
short = TMP / "short"
(short / "work").mkdir(parents=True)
(short / "work" / "transcript.raw.txt").write_text("\n\n".join(raw_para(s) for s in range(0, 600, 30)) + "\n", encoding="utf-8")
check(P.split_transcript(short)["total"] == 1, "a 10 minute episode is one chunk")
# legacy / single-call episodes (edited transcript without chunks) still count as edited
legacy = fixture.build(TMP / "pipeline-legacy")
st = P.episode_status(legacy)
check("edit_transcript" in st["done"] and st["step"] != "transcript", f"legacy episode: {st['step']} {st['done']}")

# --- progress, deferred gates -------------------------------------------------------------------------
P.record_progress(long_ep, "chunk-04", error="timeout")
P.record_progress(long_ep, "chunk-04", error="timeout")
check(P.load_progress(long_ep)["steps"]["chunk-04"]["attempts"] == 2, "attempts are counted")
gate_ep = fixture.build(TMP / "pipeline-gate")
ep = L.load_json(gate_ep / "work/episode.json")
ep["gates"] = {"A": "", "youtube": "", "wordpress": ""}
(gate_ep / "work/episode.json").write_text(json.dumps(ep, ensure_ascii=False), encoding="utf-8")
st = P.episode_status(gate_ep)
check(st["step"] == "gate_A" and st["pending_gate"] == "A", f"stops at Gate A: {st['step']}")
P.record_progress(gate_ep, "gate_A", defer_gate="A")
st = P.episode_status(gate_ep)
check(st["step"] != "gate_A" and st["open_gates"] == ["A"], f"unattended run continues, the gate stays open: {st['step']}")
ep["gates"]["A"] = "user 2026-10-22"
(gate_ep / "work/episode.json").write_text(json.dumps(ep, ensure_ascii=False), encoding="utf-8")
check(P.episode_status(gate_ep)["open_gates"] == [], "an approved gate is no longer open")
L.render_package(gate_ep, L.load_brand(gate_ep / "brand.json"), ["youtube"])
res = L.validate_package(gate_ep, L.load_brand(gate_ep / "brand.json"), ["youtube"])
L.write_review(gate_ep, L.load_brand(gate_ep / "brand.json"), res)
st = P.episode_status(gate_ep)
check(st["step"] == "gate_youtube" and st["pending_gate"] == "youtube", f"rendered -> waits for approval: {st['step']}")
ep["gates"]["youtube"] = "user 2026-10-22"
(gate_ep / "work/episode.json").write_text(json.dumps(ep, ensure_ascii=False), encoding="utf-8")
check(P.episode_status(gate_ep)["step"] == "done", "all gates approved -> done")

# --- latest unfinished episode under the episodes root -------------------------------------------------
root = TMP / "pipeline-root"
(root / "_other").mkdir(parents=True)
os.replace(long_ep, root / "_other" / "2026-10-other-01-long")
os.replace(gate_ep, root / "_other" / "2026-10-other-02-done")
L.USER_DIR.mkdir(parents=True, exist_ok=True)
cfg_file = L.USER_DIR / "config.json"
cfg_before = cfg_file.read_text(encoding="utf-8") if cfg_file.exists() else None
cfg_file.write_text(json.dumps({"episodes_root": str(root)}), encoding="utf-8")
found = P.find_unfinished()
check(found and found["episode_dir"].endswith("2026-10-other-01-long"), f"find_unfinished skips the done episode: {found}")
if cfg_before is None:
    cfg_file.unlink()
else:
    cfg_file.write_text(cfg_before, encoding="utf-8")

# --- models: plugin defaults unless the user overrides -------------------------------------------------
m = L.resolve_models()
check(m["profile"] == "balanced" and m["profile_source"] == "default" and not m["errors"], f"default models: {m}")
check(all(o["source"] == "default" for o in m["operations"].values()) and m["operations"]["transcript_edit"]["fallback"] == "opus",
      "no user choice -> plugin defaults, with a fallback tier")
m = L.resolve_models({"profile": "fast", "overrides": {"aeo_review": "opus", "bogus": "opus", "transcript_edit": "gpt"}})
check(m["profile"] == "fast" and m["operations"]["transcript_edit"] == {**m["operations"]["transcript_edit"], "model": "haiku", "source": "profile"}
      and m["operations"]["aeo_review"]["model"] == "opus" and m["operations"]["aeo_review"]["source"] == "override"
      and len(m["errors"]) == 2, f"profile + override, bad entries reported not applied: {m}")
check(L.setup_status()["models"]["profile_source"] == "default", "setup_status carries the models")
bad = L.save_setup(models={"profile": "turbo"})
check(not bad["ok"] and any("models.profile" in e for e in bad["errors"]), "invalid models profile rejected")
ok = L.save_setup(models={"profile": "quality", "overrides": {"transcript_edit": "haiku"}})
check(ok["ok"] and ok["models"]["operations"]["transcript_edit"]["source"] == "override"
      and ok["models"]["operations"]["knowledge_map_sections"]["model"] == "opus", f"models saved: {ok.get('models')}")
check(L.load_json(L.USER_DIR / "config.json")["models"]["profile"] == "quality", "models stored in config.json")
ok = L.save_setup(models={})
check(ok["ok"] and ok["models"]["profile_source"] == "default" and "models" not in L.load_config(), "models {} resets to defaults")

# --- launcher and SessionStart check without python3 on PATH (Windows-like) --------------------------
def tool_path(extra):
    """A PATH holding only the POSIX tools the scripts use, plus `extra` (name -> executable or script text)."""
    bindir = Path(tempfile.mkdtemp(prefix="v2a-path-"))
    for tool in ("sh", "tr", "dirname", "cat"):
        (bindir / tool).symlink_to(shutil.which(tool))
    for name, target in extra.items():
        if target is None:
            continue
        if target.startswith("#!"):
            (bindir / name).write_text(target)
            (bindir / name).chmod(0o755)
        else:
            (bindir / name).symlink_to(target)
    return bindir

def run_sh(script, bindir, stdin=""):
    env = {"PATH": str(bindir), "HOME": str(TMP), "VIDEO2AEO_HOME": str(TMP / "no-home")}
    return subprocess.run([str(bindir / "sh"), str(script)], input=stdin, capture_output=True, text=True,
                          env=env, timeout=30)

INIT = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'
only_python = tool_path({"python": sys.executable})                       # `python` exists, `python3` does not
r = run_sh(ROOT / "server" / "launch.sh", only_python, INIT)
check(r.returncode == 0 and '"video2aeo"' in r.stdout, f"launcher must fall back to `python`: {r.stdout!r} {r.stderr!r}")
store_stub = tool_path({"python": "#!/bin/sh\nexit 9\n"})              # Microsoft Store stub: opens the Store, fails
r = run_sh(ROOT / "server" / "launch.sh", store_stub, INIT)
check(r.returncode == 1 and "Python 3.9" in r.stderr, f"launcher with no usable Python must explain: {r.stderr!r}")
for label, bindir in (("python", only_python), ("stub", store_stub), ("none", tool_path({}))):
    r = run_sh(ROOT / "hooks" / "check-deps.sh", bindir)
    check(r.returncode == 0, f"check-deps.sh must always exit 0 ({label}): {r.returncode}")
    check(("FAILED" in r.stdout) == (label != "python"), f"check-deps.sh message ({label}): {r.stdout!r}")
(TMP / "no-home").mkdir(exist_ok=True)
run_sh(ROOT / "hooks" / "check-deps.sh", only_python)
(TMP / "no-home" / "last_python").write_text("/old/python\n")
r = run_sh(ROOT / "hooks" / "check-deps.sh", only_python)
check("changed" in r.stdout and r.returncode == 0, f"changed Python must be reported: {r.stdout!r}")
mcp = L.load_json(ROOT / ".mcp.json")["mcpServers"]["video2aeo"]
check(mcp["command"] == "sh" and mcp["args"][0].endswith("server/launch.sh"), "mcp.json starts the launcher")
hooks = L.load_json(ROOT / "hooks" / "hooks.json")["hooks"]
check(set(hooks) == {"SessionStart"}, "plugin ships only a SessionStart hook (no blocking PreToolUse guards)")

if "--write-article" in sys.argv:
    out = Path(sys.argv[sys.argv.index("--write-article") + 1])
    out.parent.mkdir(parents=True, exist_ok=True)
    brand["description"].update(promo="", promo_position="end")
    L.render_package(ep_dir, brand, ["wordpress"])
    out.write_bytes((ep_dir / "article.wp.html").read_bytes())

print(f"smoke: {checks} checks ok")
