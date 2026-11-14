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
import aeo_setup as S  # noqa: E402
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
env = S.check_environment()
check(env["ok"] and env["python"]["ok"], f"check_environment not ok: {env['problems']}")
check(set(env) == {"ok", "problems", "python", "user_dir", "user_dir_writable", "missing_subtitle_tools", "install_command"},
      f"check_environment fields: {sorted(env)}")
check(not L.PR.user_home().exists(), "check_environment must not create the settings folder")

# --- subtitle tools: offered, never installed silently; the installer is exercised with pip mocked ------------
import aeo_net as N
import importlib.util as _iu
real_find, real_run, real_which, real_access = _iu.find_spec, N.subprocess.run, N.shutil.which, N.os.access
real_mod, real_ext = sys.modules.get("youtube_transcript_api"), S.externally_managed
check(env["missing_subtitle_tools"] == [p for m, p in S.SUBTITLE_PACKAGES.items() if real_find(m) is None],
      "check_environment must list the missing subtitle packages")
_iu.find_spec = lambda name, *a, **k: None if name in S.SUBTITLE_PACKAGES else real_find(name, *a, **k)
S.externally_managed = lambda: False
try:
    env_missing = S.check_environment()
    check(env_missing["missing_subtitle_tools"] == ["youtube-transcript-api", "yt-dlp"]
          and "pip" in env_missing["install_command"] and sys.executable in env_missing["install_command"],
          f"install_command must use this interpreter: {env_missing['install_command']}")
    calls = []
    def fake_run(cmd, **k):
        calls.append((cmd, k))
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": "no network"})()
    N.subprocess.run = fake_run
    res = N.install_subtitle_tools()
    check(calls and calls[0][0][:4] == [sys.executable, "-m", "pip", "install"] and "youtube-transcript-api" in calls[0][0],
          f"pip must run in this interpreter: {calls}")
    check(calls[0][1].get("stdin") is N.subprocess.DEVNULL, "pip must not inherit the MCP stdin")
    check(res["ok"] is False and res["still_missing"] == ["youtube-transcript-api", "yt-dlp"] and "manual_command" in res,
          f"failed install must report the manual command: {res}")
    S.externally_managed = lambda: True                                   # Homebrew / distro Python: pip is refused
    calls.clear()
    res = N.install_subtitle_tools()
    check(not calls and res["ok"] is False and "yt-dlp" in res["manual_command"] and "pip install" not in res["manual_command"],
          f"externally managed Python must not run pip and must suggest another install: {res}")
    S.externally_managed = lambda: False
    N.shutil.which = lambda name: None
    N.os.access = lambda p, m: False
    sys.modules["youtube_transcript_api"] = None  # makes `import youtube_transcript_api` raise ImportError, no network
    fail = N.fetch_transcript("https://www.youtube.com/watch?v=abcdefghijk", TMP / "t", "bg")
    check(fail["ok"] is False and fail.get("missing_subtitle_tools") == ["youtube-transcript-api", "yt-dlp"]
          and "can_auto_install" not in fail, f"no usable tool must list both as missing: {fail}")
    N.os.access = lambda p, m: p == "/opt/homebrew/bin/yt-dlp"            # brew yt-dlp outside the app's PATH
    check(N._ytdlp_cmd() == ["/opt/homebrew/bin/yt-dlp"], f"Homebrew yt-dlp must be found: {N._ytdlp_cmd()}")
    def slow_run(cmd, **k):
        raise N.subprocess.TimeoutExpired(cmd, 180)
    N.subprocess.run = slow_run
    fail = N.fetch_transcript("https://www.youtube.com/watch?v=abcdefghijk", TMP / "t", "bg")
    check(fail["ok"] is False and "fallback" in fail and any("TimeoutExpired" in e for e in fail["errors"])
          and "missing_subtitle_tools" not in fail,
          f"a yt-dlp timeout must end in the manual fallback, not an exception: {fail}")
finally:
    _iu.find_spec, N.subprocess.run, N.shutil.which, N.os.access = real_find, real_run, real_which, real_access
    S.externally_managed = real_ext
    if real_mod is None:
        sys.modules.pop("youtube_transcript_api", None)
    else:
        sys.modules["youtube_transcript_api"] = real_mod

import subprocess

# --- first run: not configured, nothing written ---------------------------------------------------
st = L.setup_status()
check(not st["configured"] and not st["setup_completed"], "fresh folder must not be configured")
check(st["required_missing"] == ["channel", "topics"], f"required_missing: {st['required_missing']}")
check(L.save_setup()["ok"] is False, "empty save_setup must fail")
check(not L.PR.user_home().exists(), "failed save_setup must not write")
bad = L.save_setup(brand={"channel": "X"}, guidelines_off=["number-traceability"])
check(bad["ok"] is False and "Unknown or locked" in bad["errors"][0], "locked/unknown guideline id must be rejected")
check(L.save_setup(brand={"description": {"promo_position": "middle"}})["ok"] is False, "bad promo_position rejected")

# --- skipping optional fields still reaches configured; dotted keys are expanded ------------------
r = L.save_setup(brand={"channel": "Demo", "topics": "money", "description.promo": "PROMO TEXT"},
                 guidelines_md="# House\n", guidelines_off=["euro-equivalents"])
check(r["ok"] and r["configured"], f"setup with skipped optional fields must be configured: {r.get('missing')}")
saved = L.load_json(L.settings_dir() / "brand.json")
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
check(L.load_json(L.settings_dir() / "brand.json")["description"]["promo"] == "PROMO TEXT", "promo lost on re-run")
L.save_setup(guidelines_md="# House v2\n")
check((L.settings_dir() / "guidelines.md.bak").read_text(encoding="utf-8") == "# House\n", "guidelines.md not backed up")
check(L.setup_status()["current"]["guidelines_md"] == "# House v2\n", "status must return current guidelines")

# --- damaged files: status reports, save repairs ----------------------------------------------------
(L.settings_dir() / "setup.json").write_text('{"compl', encoding="utf-8")
st = L.setup_status()
check(not st["configured"] and st["unreadable"], "corrupt setup.json must be reported, not raised")
(L.settings_dir() / "brand.json").write_text("not json", encoding="utf-8")
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
projp = L.settings_dir() / "project.json"
proj_before = L.load_json(projp)
r = L.save_setup(brand={"formats": {"clips": {"label": "Clips", "folder": "clips"}}}, episodes_root=str(root))
check(r["ok"] and r["current"]["episodes_root"] == str(root.resolve()), f"episodes_root not saved: {r.get('errors')}")
check(L.load_json(projp) == proj_before, "a profile project keeps its episodes folder in this computer's list, not in project.json")
check(L.PR.list_projects()[0]["episodes_root"] == str(root.resolve()), "episodes_root in projects.json")
check(r["current"]["series_folders"] == {"clips": "clips"}, f"series_folders: {r['current']['series_folders']}")
check(L.save_setup(brand={"formats": {"talk": {"label": "Talk", "folder": "clips"}}})["ok"] is False, "duplicate series folder rejected")

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
(other.parent / "outside-ep" / "work").mkdir(parents=True)
(other.parent / "outside-ep" / "work" / "episode.json").write_text("{}", encoding="utf-8")
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
check(L.check_episode_dir(TMP / "outside-ep") is None, "existing episode outside the root may be resumed")
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
inline = desc(footer="Line\n____________\nADS IN FOOTER\n____________\nEnd", promo="ADS IN FOOTER")
check(L._promo_and_footer(inline)[1].count("ADS IN FOOTER") == 1, "a footer that already holds the promo must not duplicate it")
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

# --- empty brand glossary is reported ---------------------------------------------------------------
check(any("glossary" in w for w in L.setup_status()["warnings"]) or L.setup_status()["glossary_entries"] > 0,
      "empty glossary must warn")

# --- optional yt-dlp cookies from config.json --------------------------------------------------------
import aeo_net as N  # noqa: E402
cfgp = L.PR.user_home() / "config.json"
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
# single-call episodes (edited transcript without chunks) count as edited
single = fixture.build(TMP / "pipeline-single")
st = P.episode_status(single)
check("edit_transcript" in st["done"] and st["step"] != "transcript", f"single-call episode: {st['step']} {st['done']}")

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
root_before = str(L.episodes_root())
L.PR.set_machine_value(L.PR.active(), "episodes_root", str(root))
found = P.find_unfinished()
check(found and found["episode_dir"].endswith("2026-10-other-01-long"), f"find_unfinished skips the done episode: {found}")
L.PR.set_machine_value(L.PR.active(), "episodes_root", root_before)

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
check(L.load_json(L.settings_dir() / "project.json")["models"]["profile"] == "quality", "models stored in project.json")
ok = L.save_setup(models={})
check(ok["ok"] and ok["models"]["profile_source"] == "default" and "models" not in L.team_config(), "models {} resets to defaults")

# --- import of a settings folder and a zip without manifest, unrecognised keys, empty disclaimer line --------------
import zipfile  # noqa: E402
set_dir = TMP / "settings-folder"
set_dir.mkdir()
(set_dir / "brand.json").write_text(json.dumps({"channel": "Folder Show", "podcast": {"host": "A"}, "description": {"disclaimer_url": ""}}), encoding="utf-8")
(set_dir / "glossary.json").write_text(json.dumps({"fixes": [["x", "y"]]}), encoding="utf-8")
(set_dir / "guidelines.md").write_text("# Rules\n", encoding="utf-8")
(set_dir / "other.txt").write_text("ignored", encoding="utf-8")
with zipfile.ZipFile(TMP / "plain.zip", "w") as z:
    for f in ("brand.json", "glossary.json", "guidelines.md", "other.txt"):
        z.write(set_dir / f, f"Archive/{f}")
for src in (set_dir, TMP / "plain.zip"):
    b = S.read_setup_bundle(str(src))
    check(b["ok"] and b["found"] == ["brand.json", "glossary.json", "guidelines.md"] and b["brand"]["channel"] == "Folder Show"
          and b["guidelines_md"].startswith("# Rules") and b["unrecognised_keys"] == ["podcast"], f"bundle from {src.name}: {b}")
check(not S.read_setup_bundle(str(TMP / "nothing-here"))["ok"], "missing bundle path")
(TMP / "empty-dir").mkdir()
check(not S.read_setup_bundle(str(TMP / "empty-dir"))["ok"], "folder without setup files")
saved = L.save_setup(brand=b["brand"], glossary=b["glossary"], guidelines_md=b["guidelines_md"])
check(saved["ok"] and saved["unrecognised_keys"] == ["podcast"], f"save_setup reports unrecognised keys: {saved.get('errors')}")
top, foot = L._promo_and_footer(desc(disclaimer_url=""))
check("отказ от отговорност" not in foot and "{DISCLAIMER_URL}" not in foot, f"empty disclaimer line must be dropped: {foot!r}")

# --- setup archive: export on one computer, review + replace-import on another ------------------------------------
real_home = os.environ["VIDEO2AEO_HOME"]
def use_home(name):
    os.environ["VIDEO2AEO_HOME"] = str(TMP / name)
    L.PR.reset_active()
    return TMP / name
try:
    a = use_home("team-a")
    (TMP / "eps-a").mkdir()
    r = L.save_setup(brand={"channel": "Тестов канал", "topics": "money", "description.promo": "PROMO"},
                     glossary={"fixes": [["a", "b"]]}, guidelines_md="# House rules\n",
                     guidelines_files={"youtube-description.md": "# YT additions\n"},
                     guidelines_off=[L.ADJUSTABLE_GUIDELINES[0]], episodes_root=str(TMP / "eps-a"),
                     models={"profile": "fast"})
    check(r["ok"] and r["configured"], f"team-a setup: {r.get('errors') or r.get('missing')}")
    L.save_setup(brand={"site": {"base_url": "https://wp.example"}})
    creds = L.PR.active().credentials_path()
    creds.parent.mkdir(parents=True, exist_ok=True)
    creds.write_text(json.dumps({"wordpress": {"base_url": "https://wp.example", "username": "ed",
                                               "app_password": "SECRET-PASS-123"}}), encoding="utf-8")
    (a / "config.json").write_text(json.dumps({"youtube": {"cookies_file": "/Users/someone/cookies-SECRET.txt"}}), encoding="utf-8")
    (TMP / "share").mkdir()
    ex = S.export_setup(str(TMP / "share"))
    check(ex["ok"] and Path(ex["path"]).name.startswith("video2aeo-setup-testov-kanal-") and not ex["warnings"],
          f"export (transliterated name, no warning for the public WordPress address): {ex}")
    with zipfile.ZipFile(ex["path"]) as z:
        names = sorted(z.namelist())
        blob = b"".join(z.read(n) for n in names)
    check(names == ["brand.json", "glossary.json", "guidelines.md", "guidelines/youtube-description.md",
                    "video2aeo-setup.json"], f"archive names: {names}")
    check(b"SECRET-PASS-123" not in blob and b"cookies-SECRET" not in blob and str(TMP / "eps-a").encode() not in blob,
          "archive must not hold credentials or the episodes folder")
    ex2 = S.export_setup(str(TMP / "share"))
    check(ex2["ok"] and ex2["path"] != ex["path"] and Path(ex["path"]).exists(), "second export must not overwrite")
    check(not S.export_setup("relative/dir")["ok"], "export needs an absolute folder")

    b = use_home("team-b")
    (TMP / "eps-b").mkdir()
    check(not S.export_setup(str(TMP / "share"))["ok"], "export before setup must fail")
    imp = S.read_setup_bundle(ex["path"])
    check(imp["ok"] and imp["guidelines_off"] == [L.ADJUSTABLE_GUIDELINES[0]] and imp["models"] == {"profile": "fast"}
          and imp["guidelines_files"] == {"youtube-description.md": "# YT additions\n"} and not imp["dropped"],
          f"import of the export: {imp}")
    r = L.save_setup(brand=imp["brand"], glossary=imp["glossary"], guidelines_md=imp["guidelines_md"],
                     guidelines_files=imp["guidelines_files"], guidelines_off=imp["guidelines_off"], models=imp["models"],
                     episodes_root=str(TMP / "eps-b"), replace=True)
    check(r["ok"] and r["configured"] and (L.settings_dir() / "guidelines" / "youtube-description.md").read_text() == "# YT additions\n"
          and "backup" not in r, f"replace-import into an empty home: {r.get('errors')}")
    same = ("configured", "guidelines_off", "models", "glossary_entries")
    status_b = {k: r[k] for k in same}
    use_home("team-a")
    status_a = L.setup_status()
    cur_a = {k: v for k, v in status_a["current"].items() if k != "episodes_root"}
    cur_b = {k: v for k, v in r["current"].items() if k != "episodes_root"}
    check(status_b == {k: status_a[k] for k in same} and cur_a == cur_b, "imported setup must equal the exported one")
    use_home("team-b")

    # replace over a configured home with a minimal archive clears what the archive does not carry
    (TMP / "mini").mkdir()
    (TMP / "mini" / "brand.json").write_text("﻿" + json.dumps({"channel": "Mini", "topics": "t"}), encoding="utf-8")
    mini = S.read_setup_bundle(str(TMP / "mini"))
    check(mini["ok"] and "models" not in mini and "guidelines_off" not in mini, f"BOM brand-only folder: {mini}")
    r = L.save_setup(brand=mini["brand"], replace=True)
    bs = L.settings_dir()
    check(r["ok"] and r.get("backup") and not (bs / "guidelines.md").exists()
          and not list((bs / "guidelines").glob("*.md")) and L.load_json(bs / "glossary.json") == {}
          and r["guidelines_off"] == [] and "models" not in L.team_config()
          and L.episodes_root(), f"replace must clear and back up: {r.get('errors')}")
    first_backup = Path(r["backup"])
    check((first_backup / "guidelines" / "youtube-description.md").exists() and (first_backup / "glossary.json").exists()
          and L.load_json(first_backup / "config.json") == {"models": {"profile": "fast"}},
          "backup holds the replaced files and only the models of config.json")
    r2 = L.save_setup(brand=mini["brand"], replace=True)
    check(r2["ok"] and r2["backup"] != r["backup"] and (first_backup / "guidelines.md").exists(), "second import keeps the first backup")
    undo = S.read_setup_bundle(str(first_backup))
    check(undo["ok"] and undo["brand"]["channel"] == "Тестов канал" and undo["models"] == {"profile": "fast"},
          f"a backup folder can be imported to undo: {undo}")

    # tolerant import: newer format, unknown ids; earlier install with credentials
    with zipfile.ZipFile(TMP / "newer.zip", "w") as z:
        z.writestr("video2aeo-setup.json", json.dumps({"archive_format": 99, "guidelines_off": ["no-such-rule"],
                                                       "models": {"profile": "turbo", "overrides": {"edit": "gpt"}}}))
        z.writestr("brand.json", json.dumps({"channel": "N"}))
    nw = S.read_setup_bundle(str(TMP / "newer.zip"))
    check(nw["ok"] and nw["warnings"] and nw["guidelines_off"] == [] and nw["models"] == {} and len(nw["dropped"]) == 3,
          f"newer archive: {nw}")
    leg = TMP / "earlier" / ".video2aeo"
    leg.mkdir(parents=True)
    (leg / "brand.json").write_text(json.dumps({"channel": "E"}), encoding="utf-8")
    (leg / "setup.json").write_text(json.dumps({"guidelines_off": [L.ADJUSTABLE_GUIDELINES[0]]}), encoding="utf-8")
    (leg / "config.json").write_text(json.dumps({"models": {"profile": "quality"}, "wordpress": {"app_password": "X-SECRET"}}),
                                     encoding="utf-8")
    el = S.read_setup_bundle(str(TMP / "earlier"))
    check(el["ok"] and el["guidelines_off"] == [L.ADJUSTABLE_GUIDELINES[0]] and el["models"] == {"profile": "quality"}
          and any("NOT imported" in w for w in el["warnings"]) and "X-SECRET" not in json.dumps(el), f"earlier install: {el}")

    # hostile archives are refused as a whole
    def zip_with(name, entries):
        path = TMP / name
        with zipfile.ZipFile(path, "w") as z:
            for n, body in entries:
                z.writestr(n, body)
        return str(path)
    link = zipfile.ZipInfo("brand.json")
    link.external_attr = (0o120777 << 16)
    corrupt = zip_with("h6.zip", [("brand.json", "{" + '"channel": "x", ' * 200 + '"a": 1}')])
    raw = bytearray(Path(corrupt).read_bytes())
    raw[60:80] = b"\xff" * 20                                   # damage the compressed data of the member
    Path(corrupt).write_bytes(bytes(raw))
    before = sorted(p.name for p in b.iterdir())
    for label, path, reason in (("traversal", zip_with("h1.zip", [("../brand.json", "{}")]), "unsafe"),
                                ("absolute", zip_with("h2.zip", [("/etc/brand.json", "{}")]), "unsafe"),
                                ("symlink", zip_with("h3.zip", [(link, "/etc/passwd")]), "link"),
                                ("oversized", zip_with("h4.zip", [("brand.json", "x" * (S.ARCHIVE_MAX_FILE + 1))]), "too large"),
                                ("many", zip_with("h5.zip", [(f"f{i}.txt", "") for i in range(S.ARCHIVE_MAX_MEMBERS + 1)]), "too many"),
                                ("corrupt", corrupt, "Could not read"),
                                ("dotted clash", zip_with("h7.zip", [("brand.json", json.dumps({"a": 1, "a.b": 2}))]), "Could not read")):
        res = S.read_setup_bundle(path)
        check(not res["ok"] and reason in " ".join(res["errors"]), f"hostile archive ({label}) must be refused: {res}")
    check(sorted(p.name for p in b.iterdir()) == before, "reading archives must not write anything")
    finder = zip_with("finder.zip", [("Team/brand.json", json.dumps({"channel": "F"})), ("__MACOSX/Team/._brand.json", "junk")])
    fz = S.read_setup_bundle(finder)
    check(fz["ok"] and fz["brand"]["channel"] == "F" and fz["found"] == ["brand.json"], f"Finder zip with a wrapping folder: {fz}")
    check(not L.save_setup(brand={"channel": "x"}, guidelines_files={"a.md\n": "x"})["ok"], "file name with a newline rejected")
    check(not S.read_setup_bundle("  ")["ok"], "empty path must be refused")
    check(not L.save_setup(brand={"channel": "x"}, guidelines_files={"../evil.md": "x"})["ok"], "unsafe guideline file name rejected")

    # a failed replace keeps the backup, says where it is, and does not count as configured
    real_write = L._write_atomic
    def failing_write(path, text):
        if path.name == "glossary.json":
            raise OSError("disk full")
        real_write(path, text)
    L._write_atomic = failing_write
    try:
        bad = L.save_setup(brand=mini["brand"], glossary={"fixes": []}, replace=True)
    finally:
        L._write_atomic = real_write
    check(not bad["ok"] and bad.get("backup") and Path(bad["backup"]).is_dir() and not bad["configured"]
          and any("restore" in e for e in bad["errors"]), f"failed replace: {bad}")

    # Cyrillic guideline file names travel through export and import; Git Bash paths work on Windows
    use_home("team-c")
    (TMP / "eps-c").mkdir()
    L.save_setup(brand={"channel": "C", "topics": "t"}, guidelines_files={"правила за тон.md": "# Тон\n"},
                 episodes_root=str(TMP / "eps-c"))
    exc = S.export_setup(str(TMP / "share"))
    cyr = S.read_setup_bundle(exc["path"])
    check(cyr["ok"] and cyr["guidelines_files"] == {"правила за тон.md": "# Тон\n"}, f"Cyrillic guideline file: {cyr}")
    real_os_name = L.os.name
    L.os.name = "nt"
    try:
        check(L.native_path("/c/Users/x/Desktop") == "C:\\Users\\x\\Desktop" and L.native_path("C:\\a") == "C:\\a"
              and L.native_path("/Users/x") == "/Users/x", "Git Bash paths become Windows paths")
    finally:
        L.os.name = real_os_name

    # export warns about credential-looking content
    use_home("team-a")
    L.save_setup(brand={"organization": {"api_key": "k"}})
    ex3 = S.export_setup(str(TMP / "share"))
    check(ex3["ok"] and any("credentials" in w for w in ex3["warnings"]), f"secret-like key must warn: {ex3['warnings']}")
finally:
    os.environ["VIDEO2AEO_HOME"] = real_home
    L.PR.reset_active()

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
for answer, expect_fail in (("on-path", False), ("found:C:\\Git\\bin", True), ("git-missing", True)):  # Windows PATH check
    args_log = TMP / f"ps-args-{answer[:5]}.txt"
    win = tool_path({"python": sys.executable, "uname": "#!/bin/sh\necho MINGW64_NT-10.0\n", "cygpath": "#!/bin/sh\necho \"$2\"\n",
                     "powershell.exe": f"#!/bin/sh\necho \"$*\" > '{args_log}'\nprintf '%s\\n' '{answer}'\n"})
    r = run_sh(ROOT / "hooks" / "check-deps.sh", win)
    check(r.returncode == 0 and ("FAILED" in r.stdout) == expect_fail and (not expect_fail or "doctor" in r.stdout),
          f"Windows sh-on-PATH check ({answer}): {r.stdout!r}")
    check(("video2aeo-path-fix: C:\\Git\\bin" in r.stdout) == answer.startswith("found:"),
          f"the fixable folder must be on its own line for doctor ({answer}): {r.stdout!r}")
    check("-ShFolder" in args_log.read_text(), f"the hook must pass the folder of its own sh: {args_log.read_text()!r}")
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
