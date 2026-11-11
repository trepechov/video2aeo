#!/usr/bin/env python3
"""
Smoke checks for several projects on one computer and the conversion of a 0.9 single-project folder (dev-only).
Runs against temporary VIDEO2AEO_HOME folders, never ~/.video2aeo/. Python 3.9+, stdlib only.

  python3 dev/smoke_projects.py     # prints "smoke_projects: N checks ok" or the first failure
"""
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="video2aeo-projects-")).resolve()
os.environ["VIDEO2AEO_HOME"] = str(TMP / "home")
os.environ.pop("VIDEO2AEO_PROJECT", None)
sys.path.insert(0, str(ROOT / "scripts"))
import aeo_lib as L  # noqa: E402
import aeo_net as N  # noqa: E402
import aeo_project as PR  # noqa: E402

checks = 0


def check(cond, msg):
    global checks
    if not cond:
        sys.exit(f"smoke_projects FAILED: {msg}")
    checks += 1


def use_home(name):
    os.environ["VIDEO2AEO_HOME"] = str(TMP / name)
    PR.reset_active()
    return TMP / name


def snapshot(folder: Path) -> dict:
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def at(path):
    """Resolve the project of a folder and make it the active one."""
    p = PR.resolve(str(path))
    PR.set_active(p)
    return p


# --- 1. a 0.9 user folder is converted into the first project; its files stay where they are -------------------
home = use_home("home-09")
eps = TMP / "eps-09"
(eps / "_other" / "2026-10-other-01-old" / "work").mkdir(parents=True)
(eps / "_other" / "2026-10-other-01-old" / "work" / "episode.json").write_text("{}", encoding="utf-8")
(home / "guidelines").mkdir(parents=True)
(home / "backup-20261001-120000").mkdir()
(home / "tools-venv").mkdir()
files = {
    "brand.json": {"channel": "Old Show", "topics": "money", "organization": {"name": "", "logo": ""},  # as 0.9 saved it
                   "description": {"promo": "OLD PROMO", "schedule": "", "disclaimer_url": "", "social_links": ""}},
    "glossary.json": {"names": ["Ivan"]},
    "setup.json": {"completed": "2026-10-01", "guidelines_off": [L.ADJUSTABLE_GUIDELINES[0]]},
    "config.json": {"episodes_root": str(eps), "models": {"profile": "fast"},
                    "wordpress": {"base_url": "https://wp.example", "username": "ed", "app_password": "SECRET-1"},
                    "youtube": {"cookies_from_browser": "firefox"}},
}
for n, data in files.items():
    (home / n).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
(home / "guidelines.md").write_text("# House\n", encoding="utf-8")
(home / "guidelines" / "youtube-description.md").write_text("# YT\n", encoding="utf-8")
(home / "backup-20261001-120000" / "brand.json").write_text("{}", encoding="utf-8")
(home / "Archive.zip").write_bytes(b"PK user file")
(home / "config.json.broken").write_text('{"wordpress": {"app_password": "SECRET-1"}', encoding="utf-8")
(home / "glossary.json.broken").write_text("old", encoding="utf-8")
(home / "last_python").write_text("/usr/bin/python3\n", encoding="utf-8")
before = snapshot(home)

p = at(TMP)  # any folder: there is only one project after the conversion
check(p is not None and p.id == "old-show" and p.location == "profile" and p.found_by == "only", f"converted project: {p and p.summary()}")
st = L.setup_status()
check(st["configured"] and st["current"]["channel"] == "Old Show" and st["current"]["promo"] == "OLD PROMO",
      f"converted settings are configured as before: {st.get('missing')} {st.get('unreadable')}")
check(st["guidelines_off"] == [L.ADJUSTABLE_GUIDELINES[0]] and st["models"]["profile"] == "fast"
      and st["current"]["guidelines_md"] == "# House\n" and st["glossary_entries"] == 1, "every team value survives")
check(st["current"]["episodes_root"] == str(eps), f"episodes folder kept: {st['current']['episodes_root']}")
check(st["migrated"] and st["migrated"]["from"] == "0.9" and st["migrated"]["old_files"] == str(home), f"notice: {st['migrated']}")
sd = Path(st["settings_dir"])
check(sd == (home / "projects" / "old-show").resolve(), f"settings folder: {sd}")
check((sd / "guidelines" / "youtube-description.md").read_text() == "# YT\n" and (sd / "backup-20261001-120000" / "brand.json").exists(),
      "guidelines/ and backups are copied")
creds = home / "credentials" / "old-show.json"
check(L.load_json(creds) == {"wordpress": files["config.json"]["wordpress"]}, "WordPress sign-in moved to credentials/<id>.json")
check(stat.S_IMODE(creds.stat().st_mode) == 0o600, "credentials file is private (600)")
check(N._load_wp_config(None)["app_password"] == "SECRET-1", "wp_push_draft finds the project's sign-in")
check(N._yt_cookie_args() == ["--cookies-from-browser", "firefox"], "YouTube cookies stay computer-wide")
check(not any("SECRET-1" in p.read_text(errors="ignore") for p in sd.rglob("*") if p.is_file()),
      "no password in the settings folder (config.json.broken is not copied)")
check((sd / "glossary.json.broken").exists() and not (sd / "config.json.broken").exists(), "only team .broken files copied")
after = snapshot(home)
check(all(after.get(k) == v for k, v in before.items()), "every 0.9 file is left byte-identical in place")
check((home / PR.MOVED_NOTE).exists() and "old-show" in (home / PR.MOVED_NOTE).read_text(), "MOVED-TO-PROJECTS.txt written")
check(not (home / PR.LOCK).exists() and not list((home / "projects").glob(".*")), "no lock or temp folder left")
(home / "brand.json").write_text(json.dumps({"channel": "Edited in 0.9"}), encoding="utf-8")
check(L.load_brand()["channel"] == "Old Show", "the old flat files are not read after the conversion")
PR._MIGRATION.clear()
check(PR.ensure_migrated() == {} and len(PR.list_projects()) == 1, "a second start converts nothing")
check(L.check_episode_dir(eps / "_other" / "2026-10-other-01-old") is None, "an episode made by 0.9 is still accepted")
check(L.save_setup(brand={"topics": "money and more"})["ok"] and L.setup_status()["migrated"] is None,
      "the notice is shown until the next save")

# --- 2. a failed conversion changes nothing and keeps 0.9 working --------------------------------------------
home = use_home("home-fail")
home.mkdir()
for n, data in files.items():
    (home / n).write_text(json.dumps(data), encoding="utf-8")
before = snapshot(home)
real_copy2 = PR.shutil.copy2
def broken_copy(*a, **k):
    raise OSError("disk full")
PR.shutil.copy2 = broken_copy
try:
    p = at(TMP)
finally:
    PR.shutil.copy2 = real_copy2
st = L.setup_status()
check(p is not None and p.legacy and st["configured"] and "disk full" in st["migration_error"],
      f"failed conversion -> old folder used in place: {st['migration_error']!r}")
check(st["current"]["episodes_root"] == str(eps) and st["models"]["profile"] == "fast", "legacy read of config.json")
check(snapshot(home) == before and not (home / PR.REGISTRY).exists(), "a failed conversion writes nothing")
PR._MIGRATION.clear()
(home / PR.LOCK).write_text("")
check(PR.ensure_migrated() == {} and at(TMP).legacy, "another session converting: read the old folder this time")
(home / PR.LOCK).unlink()
p = at(TMP)
check(not p.legacy and p.id == "old-show" and (home / PR.REGISTRY).exists(), "the next start converts")

# --- 3. several projects: in the project folder, a custom folder in the monorepo, the profile -------------------
home = use_home("home-multi")
real_susp = L._is_suspicious
check(PR._folders_for(Path.home().resolve()) == [], "the home folder is never remembered as a project folder")
L._is_suspicious = lambda c, temp=True: ""  # the test folders live in the temp folder
mono = TMP / "mono"
(mono / ".git").mkdir(parents=True)
show_a, show_b, show_c = mono / "apps" / "show-a", mono / "apps" / "show-b", TMP / "podcasts" / "show-c"
for f in (show_a / "episodes", show_b / "src", show_c / "eps", TMP / "unrelated"):
    f.mkdir(parents=True)

PR.reset_active()
PR.set_active(None)
r = L.save_setup(brand={"channel": "Show A", "topics": "a"}, episodes_root=str(show_a / "episodes"),
                 create={"name": "Show A", "location": "project", "project_folder": str(show_a)})
check(r["ok"] and r["configured"] and r["project"]["settings_dir"] == str(show_a / ".video2aeo"), f"project-folder project: {r.get('errors')}")
check((show_a / ".video2aeo" / ".gitignore").read_text() == PR.GITIGNORE, ".gitignore for backups in a repo settings folder")
check(L.load_json(show_a / ".video2aeo" / "project.json")["episodes_root"] == "episodes" and not PR.load_registry()["projects"]["show-a"].get("episodes_root"),
      "episodes folder inside the project folder is shared, relative")
PR.set_active(None)
r = L.save_setup(brand={"channel": "Show B", "topics": "b"},
                 create={"name": "Show B", "location": "custom", "project_folder": str(show_b),
                         "settings_dir": str(mono / "config" / "video2aeo" / "show-b")})
check(r["ok"] and r["project"]["location"] == "custom", f"custom project: {r.get('errors')}")
check(L.load_json(show_b / ".video2aeo" / "location.json") == {"settings_dir": "../../config/video2aeo/show-b"},
      "link file with a relative path for teammates")
PR.set_active(None)
r = L.save_setup(brand={"channel": "Show C", "topics": "c"}, episodes_root=str(show_c / "eps"),
                 create={"name": "Show C", "location": "profile", "project_folder": str(show_c)})
check(r["ok"] and r["project"]["settings_dir"] == str(home / "projects" / "show-c"), f"profile project: {r.get('errors')}")
check(len(PR.list_projects()) == 3, "three projects listed")

for folder, pid, how in ((show_a / "episodes", "show-a", "folder"), (show_b / "src", "show-b", "link"),
                         (show_c / "eps", "show-c", "list"), (show_c, "show-c", "list")):
    p = PR.resolve(str(folder))
    check(p and p.id == pid and p.found_by == how, f"{folder} -> {pid} by {how}: {p and p.summary()}")
check(PR.resolve(str(TMP / "unrelated")) is None, "an unrelated folder with several projects is not guessed")
at(TMP / "unrelated")
st = L.setup_status()
check(st["project_choice_needed"] and not st["configured"] and len(st["projects"]) == 3, "the skill must ask which project")
check(L.require_setup()["setup_required"] and "which project" in L.require_setup()["error"], "output tools refuse without a project")
check(not L.save_setup(brand={"channel": "x"})["ok"], "save without a project or create is refused")
channels = {}
for folder in (show_a, show_b, show_c):
    with PR.using(PR.resolve(str(folder))):
        channels[folder.name] = L.load_brand()["channel"]
check(channels == {"show-a": "Show A", "show-b": "Show B", "show-c": "Show C"}, f"no brand mixing: {channels}")
with PR.using(PR.resolve(str(show_a))):
    check(L.episodes_root() == show_a / "episodes", "relative episodes folder resolved against the project folder")
PR.set_active(None)
taken = L.save_setup(brand={"channel": "Again"}, create={"name": "Again", "location": "project", "project_folder": str(show_a)})
check(not taken["ok"] and "already holds" in " ".join(taken["errors"]), "a folder with another project's settings is refused")
bad = L.save_setup(brand={"channel": "X"}, create={"name": "X", "location": "custom", "project_folder": str(show_c)})
check(not bad["ok"] and "settings_dir" in " ".join(bad["errors"]), "custom needs a folder")
check(not L.save_setup(brand={"channel": "X"}, create={"location": "attic"})["ok"], "unknown location refused")

# environment override (headless runs)
os.environ["VIDEO2AEO_PROJECT"] = str(show_a / ".video2aeo")
check(PR.resolve(str(show_c)).id == "show-a", "VIDEO2AEO_PROJECT wins")
del os.environ["VIDEO2AEO_PROJECT"]

# --- 4. a colleague's clone: settings found in the folder are reviewed once, then used --------------------------
clone = TMP / "clone"
shutil.copytree(mono, clone)
p = at(clone / "apps" / "show-a" / "episodes")
st = L.setup_status()
check(p.found_by == "folder" and not p.trusted and st["needs_review"] and not st["configured"], "a clone's settings need a review")
check(L.require_setup()["setup_required"] and "trust_project" in L.require_setup()["error"], "output tools wait for the review")
check(not L.save_setup(brand={"topics": "x"})["ok"], "no saving into unreviewed settings")
PR.set_active(PR.trust_project(p))
st = L.setup_status()
check(st["configured"] and st["project"]["id"] == "show-a-2" and st["current"]["channel"] == "Show A"
      and st["current"]["episodes_root"] == str(clone / "apps" / "show-a" / "episodes"),
      f"after the review the clone works with the shared episodes folder: {st['project']}")
check(PR.resolve(str(clone / "apps" / "show-a")).trusted, "reviewed once per computer")
p = at(clone / "apps" / "show-b" / "src")
check(p.found_by == "link" and not p.trusted, "a clone's linked settings need a review too")

# --- 5. moving a project's settings ------------------------------------------------------------------------
res = PR.move_project("show-c", "project", project_folder=str(show_c))
check(res["ok"] and Path(res["old_folder"]).name.startswith("show-c-moved-") and Path(res["old_folder"]).is_dir(),
      f"profile -> project folder: {res}")
p = PR.resolve(str(show_c / "eps"))
check(p.id == "show-c" and p.found_by == "folder" and p.trusted, f"found in its new place: {p.summary()}")
with PR.using(p):
    check(L.load_brand()["channel"] == "Show C" and L.episodes_root() == show_c / "eps", "brand and episodes folder kept")
res = PR.move_project("show-a", "profile")
check(res["ok"] and not (show_a / ".video2aeo").exists() and list(show_a.glob(".video2aeo-moved-*")), f"project folder -> profile: {res}")
p = PR.resolve(str(show_a / "episodes"))
check(p.id == "show-a" and p.found_by == "list", f"found through this computer's list: {p.summary()}")
with PR.using(p):
    check(L.episodes_root() == show_a / "episodes", "the shared relative episodes folder still resolves after the move")
res = PR.move_project("show-b", "profile")
check(res["ok"] and not (show_b / ".video2aeo" / "location.json").exists(), f"custom -> profile removes the link file: {res}")
check(not PR.move_project("nope", "profile")["ok"], "unknown project refused")
check(not PR.move_project("show-b", "profile")["ok"], "already there")

# --- 5b. review fixes: safe moves, damaged list, credentials, shared folders -----------------------------------
before_reg = (home / "projects.json").read_bytes()
busy = TMP / "busy"
(busy / "notes").mkdir(parents=True)
res = PR.move_project("show-b", "custom", settings_dir=str(busy), project_folder=str(show_b))
check(not res["ok"] and "not empty" in res["errors"][0] and (busy / "notes").is_dir(), f"a non-empty folder is refused: {res}")
check((home / "projects.json").read_bytes() == before_reg, "a refused move changes nothing")
src_b = Path(PR.load_registry()["projects"]["show-b"]["settings_dir"])
snap_b = snapshot(src_b)
real_replace = PR.os.replace
def fail_on_old(a, b):
    if Path(a) == src_b:
        raise OSError("folder in use")
    return real_replace(a, b)
PR.os.replace = fail_on_old
try:
    res = PR.move_project("show-b", "custom", settings_dir=str(TMP / "new-b"), project_folder=str(show_b))
finally:
    PR.os.replace = real_replace
check(not res["ok"] and "Nothing was changed" in res["errors"][0], f"failed move is undone: {res}")
check(snapshot(src_b) == snap_b and not (TMP / "new-b").exists() and (home / "projects.json").read_bytes() == before_reg
      and not list(TMP.glob(".new-b.moving-*")), "after a failed move the old folder, the list and the target are as before")

(home / "projects.json").write_text('{"projects": {', encoding="utf-8")
PR.reset_active()
st = (lambda: (PR.set_active(PR.resolve(str(show_c))), L.setup_status())[1])()
check(st["registry_error"] and "damaged" in st["registry_error"], "a damaged list is reported")
PR.set_active(None)
r = L.save_setup(brand={"channel": "Z", "topics": "z"}, create={"name": "Z", "location": "profile"})
check(not r["ok"] and (home / "projects.json").read_text() == '{"projects": {', "a damaged list is never overwritten")
(home / "projects.json").write_bytes(before_reg)

with PR.using(PR.resolve(str(show_c))):
    creds = L.PR.active().credentials_path()
    creds.parent.mkdir(parents=True, exist_ok=True)
    creds.write_text(json.dumps({"wordpress": {"app_password": "C-SECRET"}}), encoding="utf-8")
fake = TMP / "fake-repo"
(fake / ".git").mkdir(parents=True)
(fake / ".video2aeo").mkdir()
(fake / ".video2aeo" / "project.json").write_text(json.dumps({"id": "show-c", "name": "Fake",
                                                               "episodes_root": "../../outside"}), encoding="utf-8")
p = PR.resolve(str(fake))
check(p.id == "show-c" and not p.trusted and p.credentials() == {}, "a found folder never borrows another project's sign-in")
check(p.episodes_root() is None, "a shared episodes folder outside the project folder is ignored")
os.environ["VIDEO2AEO_PROJECT"] = str(fake / ".video2aeo")
check(PR.resolve(str(TMP)).credentials() == {}, "VIDEO2AEO_PROJECT settings get no sign-in")
PR.set_active(PR.resolve(str(TMP)))
(TMP / "env-eps").mkdir()
r = L.save_setup(episodes_root=str(TMP / "env-eps"))
check(not r["ok"] and "VIDEO2AEO_PROJECT" in r["errors"][0], "no silent drop of the episodes folder for env settings")
del os.environ["VIDEO2AEO_PROJECT"]
(fake / ".video2aeo" / "project.json").unlink()
(fake / ".video2aeo" / "location.json").write_text(json.dumps({"settings_dir": "../../../home-multi/projects/show-c"}),
                                                   encoding="utf-8")
check(PR.resolve(str(fake), strong_only=True) is None, "a link pointing outside its repository is ignored")

with PR.using(PR.resolve(str(show_c))):
    r = L.save_setup(episodes_root=str(show_a / "episodes"))
check(not r["ok"] and "overlaps" in " ".join(r["errors"]), f"two projects cannot share an episodes folder: {r.get('errors')}")

ren = TMP / "renamed"
shutil.copytree(show_c, ren)
shutil.rmtree(show_c)
p = PR.resolve(str(ren))
PR.set_active(p)
check(L.setup_status()["needs_review"], "a renamed folder is reviewed again")
t = PR.trust_project(p)
check(t.id == "show-c" and t.credentials()["wordpress"]["app_password"] == "C-SECRET" and len(PR.list_projects()) == 4,
      f"a renamed project keeps its id and sign-in: {t.summary()}")
shutil.move(str(ren), str(show_c))   # and back: the entry follows again
PR.trust_project(PR.resolve(str(show_c)))
check(PR.resolve(str(show_c)).trusted and PR.resolve(str(show_c / "eps")).id == "show-c", "moved back and found again")

# --- 6. the MCP server: the session's project, and no mixing with an episode of another project ----------------
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("v2a_server", ROOT / "server" / "server.py")
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)
PR.reset_active()
st = srv.call("setup_status", {"cwd": str(show_c)})
check(st["project"]["id"] == "show-c" and srv.SESSION["project"].id == "show-c", "setup_status binds the session")
with PR.using(PR.resolve(str(show_c))):
    ep = L.episode_path(L.load_brand(), None, "20261201", "first")["episode_dir"]
check(srv.call("episode_status", {"episode_dir": ep}).get("project_mismatch") is None, "own episode accepted")
srv.SESSION["project"] = None
st = srv.call("setup_status", {"cwd": str(TMP / "unrelated")})
check(st["project_choice_needed"], "unrelated folder: the user is asked")
srv.call("setup_status", {"cwd": str(TMP / "unrelated"), "project": "show-a-2"})
check(srv.SESSION["project"].id == "show-a-2", "choosing a project by id binds it")
ws = srv.call("setup_status", {"cwd": str(TMP / "unrelated")})
check(ws["project"]["id"] == "show-a-2" and not ws["project_choice_needed"], "the choice survives later calls with cwd")
mm = srv.call("workspace_status", {"cwd": str(show_c)})
check(mm.get("project_mismatch"), f"a folder of another project is refused: {mm}")
srv.call("list_projects", {"project": "show-c"})
check(srv.SESSION["project"].id == "show-a-2", "list_projects does not switch the session")
res = srv.call("render_package", {"episode_dir": ep})
check(res.get("project_mismatch") and res["episode_project"]["id"] == "show-c", f"episode of another project refused: {res}")
check({"list_projects", "trust_project", "move_project"} <= {t["name"] for t in srv.TOOLS}, "project tools listed")
check(all("cwd" in t["inputSchema"]["properties"] and "project" in t["inputSchema"]["properties"] for t in srv.TOOLS),
      "every tool takes cwd and project")
lp = srv.call("list_projects", {})
check(lp["ok"] and {p["id"] for p in lp["projects"]} >= {"show-a", "show-b", "show-c", "show-a-2"}, "list_projects")
srv.SESSION["project"] = None
r = srv.call("save_setup", {"brand": {"channel": "Show D", "topics": "d"}, "cwd": str(TMP / "unrelated"),
                            "create": {"name": "Show D", "location": "profile"}})
check(r["ok"] and r["project"]["id"] == "show-d" and srv.SESSION["project"].id == "show-d", "save_setup(create) binds the new project")

L._is_suspicious = real_susp
print(f"smoke_projects: {checks} checks ok")
