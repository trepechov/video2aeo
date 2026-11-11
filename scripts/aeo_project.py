"""
Projects of video2aeo (stdlib only): several brands/shows on one computer, each with its own settings folder.

Layout
  <user folder> = ~/.video2aeo (or VIDEO2AEO_HOME) – this computer only, never shared:
    projects.json            the projects known here: settings folder, project folders, episodes folder, trusted
    config.json              computer-wide settings (youtube cookies)
    credentials/<id>.json    per project sign-ins (wordpress), mode 600
    projects/<id>/           settings folders kept "in the profile"
  <settings folder> – team files only, safe to commit:
    project.json, brand.json, glossary.json, guidelines.md, guidelines/*.md, setup.json, .gitignore
  <project folder>/.video2aeo/ – either the settings folder itself, or location.json pointing to it (relative path)

The active project is resolved per call (resolve): VIDEO2AEO_PROJECT > the nearest .video2aeo/ above the folder >
this computer's list > the only project. A 0.9 user folder (flat brand.json, setup.json, …) is converted once into a
profile project; its files are left where they are.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import shutil
from pathlib import Path

HOME_ENV = "VIDEO2AEO_HOME"
PROJECT_ENV = "VIDEO2AEO_PROJECT"
REGISTRY = "projects.json"
PROJECT_FILE = "project.json"
LINK_FILE = "location.json"
DOT = ".video2aeo"
SETTINGS_FORMAT = 1
LOCATIONS = ("project", "profile", "custom")
# Team files of a settings folder (setup.json last: it marks setup as done).
TEAM_FILES = ("brand.json", "glossary.json", "guidelines.md", "setup.json")
# What a 0.9 user folder holds that belongs to the team setup (copied into the first project on conversion).
LEGACY_COPY = ("brand.json", "glossary.json", "guidelines.md", "guidelines.md.bak", "setup.json")
LEGACY_MARKERS = ("setup.json", "brand.json")
GITIGNORE = "# video2aeo: local backups and damaged copies are not shared\nbackup-*/\n*.bak\n*.broken\n"
MOVED_NOTE = "MOVED-TO-PROJECTS.txt"
LOCK = ".migrate.lock"


def user_home() -> Path:
    env = os.environ.get(HOME_ENV)
    return Path(env).expanduser() if env else Path.home() / ".video2aeo"


def _lib():
    import aeo_lib as L  # late import: aeo_lib imports this module
    return L


def _now() -> str:
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def _stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict, mode: int | None = None) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _lib()._write_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    if mode is not None:
        os.chmod(path, mode)


def _resolved(p) -> Path:
    return Path(_lib().native_path(str(p))).expanduser().resolve()


def _inside(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def _git_root(folder: Path):
    for d in (folder, *folder.parents):
        if (d / ".git").exists():
            return d
    return None


# ----------------------------------------------------------------------------
# Project
# ----------------------------------------------------------------------------

class Project:
    """One project as resolved for a call. `location`: project | profile | custom | legacy (an unconverted 0.9
    folder, read in place). `found_by`: env | folder | link | list | only | chosen | legacy | new."""

    def __init__(self, pid: str, name: str, settings_dir: Path, location: str, found_by: str,
                 project_folder: Path | None = None, entry: dict | None = None, trusted: bool = True):
        self.id, self.name, self.settings_dir = pid, name, Path(settings_dir)
        self.location, self.found_by, self.project_folder = location, found_by, project_folder
        self.entry, self.trusted = dict(entry or {}), trusted

    @property
    def legacy(self) -> bool:
        return self.location == "legacy"

    @property
    def key(self) -> str:
        return str(self.settings_dir)

    def team_config_path(self) -> Path:
        """project.json – or, for an unconverted 0.9 folder, its config.json."""
        return self.settings_dir / ("config.json" if self.legacy else PROJECT_FILE)

    def team_config(self) -> dict:
        return _read_json(self.team_config_path())

    def episodes_root(self):
        """This computer's choice (projects.json) wins; else the team's relative folder in project.json."""
        if self.legacy:
            v = self.team_config().get("episodes_root")
        else:
            v = self.entry.get("episodes_root") or ""
            rel = self.team_config().get("episodes_root")
            if not v and isinstance(rel, str) and rel.strip() and self.project_folder and not Path(rel).is_absolute():
                try:  # a shared folder must stay inside the project folder (the file may come from someone else)
                    cand = (self.project_folder / rel).resolve()
                    v = str(cand) if _inside(cand, Path(self.project_folder).resolve()) else ""
                except (OSError, RuntimeError):
                    v = ""
        return Path(v).expanduser() if isinstance(v, str) and v.strip() else None

    def credentials_path(self):
        """Sign-ins of this project: only for a project in this computer's list (its id there), never for settings
        merely found in a folder – their id is chosen by whoever wrote project.json."""
        if self.legacy:
            return self.settings_dir / "config.json"
        return user_home() / "credentials" / f"{self.id}.json" if self.entry else None

    def credentials(self) -> dict:
        path = self.credentials_path()
        return _read_json(path) if path else {}

    def summary(self) -> dict:
        return {"id": self.id, "name": self.name, "settings_dir": str(self.settings_dir), "location": self.location,
                "found_by": self.found_by, "project_folder": str(self.project_folder or ""), "trusted": self.trusted}


# ----------------------------------------------------------------------------
# this computer's list of projects
# ----------------------------------------------------------------------------

class RegistryDamaged(OSError):
    pass


def registry_error() -> str:
    """'' when projects.json is missing or readable, else why it cannot be used."""
    path = user_home() / REGISTRY
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        return f"{path} is damaged ({ex}); fix or restore it – nothing is written to it until then."
    return "" if isinstance(data, dict) and isinstance(data.get("projects", {}), dict) else \
        f"{path} is damaged (not a list of projects); fix or restore it – nothing is written to it until then."


def load_registry() -> dict:
    reg = _read_json(user_home() / REGISTRY)
    projects = reg.get("projects") if isinstance(reg.get("projects"), dict) else {}
    return {"version": 1, "default": reg.get("default", ""), "projects": projects}


def save_registry(reg: dict) -> None:
    err = registry_error()
    if err:  # never replace a damaged list with a partial one: every other project would be forgotten
        raise RegistryDamaged(err)
    _write_json(user_home() / REGISTRY, reg)


def _from_entry(pid: str, entry: dict, found_by: str) -> Project:
    folders = [Path(f) for f in entry.get("folders") or [] if isinstance(f, str)]
    return Project(pid, entry.get("name") or pid, Path(entry["settings_dir"]), entry.get("location", "profile"),
                   found_by, folders[0] if folders else None, entry, bool(entry.get("trusted")))


def _entry_for_settings(reg: dict, settings_dir: Path):
    for pid, e in reg["projects"].items():
        try:
            if isinstance(e, dict) and Path(e.get("settings_dir", "")).resolve() == settings_dir.resolve():
                return pid, e
        except OSError:
            continue
    return None, None


def list_projects() -> list:
    reg = load_registry()
    out = []
    for pid, e in sorted(reg["projects"].items()):
        if isinstance(e, dict) and e.get("settings_dir"):
            out.append({"id": pid, "name": e.get("name") or pid, "location": e.get("location", "profile"),
                        "settings_dir": e["settings_dir"], "folders": e.get("folders") or [],
                        "episodes_root": str(_from_entry(pid, e, "list").episodes_root() or ""),
                        "default": pid == reg["default"]})
    return out


# ----------------------------------------------------------------------------
# finding the project of a folder
# ----------------------------------------------------------------------------

def find_in_folder(path: Path):
    """The nearest <folder>/.video2aeo above `path` that holds project.json or location.json, as
    (project folder, settings folder, 'folder'|'link'). Stops before the user's home and at the disk root."""
    home = Path.home().resolve()
    for d in (path, *path.parents):
        if d == home or d == Path(d.anchor):
            return None
        dot = d / DOT
        try:
            if (dot / PROJECT_FILE).is_file():
                return d, dot, "folder"
            link = _read_json(dot / LINK_FILE) if (dot / LINK_FILE).is_file() else {}
        except OSError:
            continue
        target = link.get("settings_dir")
        if isinstance(target, str) and target.strip() and not Path(target).is_absolute():
            s = (d / target).resolve()
            boundary = _git_root(d) or d  # a link (from a clone) may only point inside its own repository
            if _inside(s, boundary.resolve()) and (s / PROJECT_FILE).is_file():
                return d, s, "link"
    return None


def _settings_project(settings: Path, project_folder, found_by: str, reg: dict) -> Project:
    pid, entry = _entry_for_settings(reg, settings)
    meta = _read_json(settings / PROJECT_FILE)
    if pid:
        p = _from_entry(pid, entry, found_by)
        p.project_folder = project_folder or p.project_folder
        return p
    pid = _lib().slugify(str(meta.get("id") or "")) or _lib().slugify(settings.parent.name) or "project"
    loc = "project" if found_by == "folder" else "custom"
    return Project(pid, meta.get("name") or pid, settings, loc, found_by, project_folder, {}, trusted=found_by == "env")


def legacy_present(home: Path | None = None) -> bool:
    home = home or user_home()
    return any((home / n).is_file() for n in LEGACY_MARKERS)


def resolve(path=None, project_id: str | None = None, strong_only: bool = False):
    """The project for a folder (or an explicit id); None when it cannot be told. strong_only: only the environment,
    a .video2aeo folder above `path` or this computer's list – no 'only project' guess (used to spot a mismatch)."""
    ensure_migrated()
    reg = load_registry()
    env = os.environ.get(PROJECT_ENV)
    if env:
        s = Path(env).expanduser().resolve()
        return _settings_project(s, None, "env", reg)
    if project_id:
        e = reg["projects"].get(project_id)
        return _from_entry(project_id, e, "chosen") if isinstance(e, dict) and e.get("settings_dir") else None
    if path:
        try:
            p = _resolved(path)
        except (OSError, RuntimeError):
            p = None
        if p is not None:
            hit = find_in_folder(p)
            if hit:
                return _settings_project(hit[1], hit[0], hit[2], reg)
            best, best_len, tie = None, -1, False
            for pid, e in reg["projects"].items():
                if not isinstance(e, dict) or not e.get("settings_dir"):
                    continue
                for f in [*(e.get("folders") or []), e.get("episodes_root") or ""]:
                    if not isinstance(f, str) or not f:
                        continue
                    try:
                        fp = Path(f).expanduser().resolve()
                    except (OSError, RuntimeError):
                        continue
                    if _inside(p, fp):
                        if len(fp.parts) > best_len:
                            best, best_len, tie = (pid, e), len(fp.parts), False
                        elif len(fp.parts) == best_len and best and best[0] != pid:
                            tie = True
            if best and not tie:
                return _from_entry(best[0], best[1], "list")
    if strong_only:
        return None
    valid = {k: e for k, e in reg["projects"].items() if isinstance(e, dict) and e.get("settings_dir")}
    if len(valid) == 1:
        pid, e = next(iter(valid.items()))
        return _from_entry(pid, e, "only")
    if not valid and legacy_present() and not (user_home() / REGISTRY).exists():  # conversion failed: read 0.9 in place
        return Project("default", "", user_home(), "legacy", "legacy")
    return None


# ----------------------------------------------------------------------------
# the active project of the current call
# ----------------------------------------------------------------------------

_UNSET = object()
_ACTIVE = _UNSET


def active():
    """The project of the running call (set by the server); else resolved from the current folder."""
    return resolve(Path.cwd()) if _ACTIVE is _UNSET else _ACTIVE


def set_active(project) -> None:
    global _ACTIVE
    _ACTIVE = project


def reset_active() -> None:
    set_active(_UNSET)


@contextlib.contextmanager
def using(project):
    global _ACTIVE
    old = _ACTIVE
    _ACTIVE = project
    try:
        yield project
    finally:
        _ACTIVE = old


# ----------------------------------------------------------------------------
# creating, trusting and moving projects
# ----------------------------------------------------------------------------

def _unique_id(reg: dict, base: str) -> str:
    pid, n = base, 1
    while pid in reg["projects"]:
        n += 1
        pid = f"{base}-{n}"
    return pid


def _folders_for(project_folder) -> list:
    """The project folder is remembered for finding the project – unless it is the home folder, Desktop, a temp
    folder or the like, which would make every session there pick this project."""
    if not project_folder:
        return []
    return [] if _lib()._is_suspicious(project_folder) else [str(project_folder)]


def _target(location: str, pid: str, project_folder, settings_dir):
    """(settings folder, errors) for a location."""
    if location not in LOCATIONS:
        return None, [f"location must be one of {list(LOCATIONS)}."]
    if location in ("project", "custom") and project_folder is None:
        return None, ["project_folder (an existing folder, absolute path) is needed for this location."]
    if location == "profile":
        return user_home() / "projects" / pid, []
    if location == "project":
        return project_folder / DOT, []
    raw = str(settings_dir or "").strip()
    if not raw:
        return None, ["settings_dir (the folder for the settings) is needed for a custom location."]
    s = Path(_lib().native_path(raw)).expanduser()
    s = (project_folder / s) if not s.is_absolute() else s
    return s.resolve(), []


def _target_errors(target: Path) -> list:
    errs = []
    if (target / PROJECT_FILE).exists():
        name = _read_json(target / PROJECT_FILE).get("name") or target
        errs.append(f"{target} already holds the settings of the project {name!r}; choose another folder.")
    clash = [n for n in TEAM_FILES if (target / n).exists()]
    if clash and not errs:
        errs.append(f"{target} already has {clash}; choose an empty or new folder.")
    try:
        if _inside(target.resolve(), user_home().resolve()) and not _inside(target.resolve(), (user_home() / "projects").resolve()):
            errs.append("The settings cannot go directly into the plugin's own user folder; choose the profile location instead.")
    except OSError:
        pass
    probe = target
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if not os.access(probe, os.W_OK):
        errs.append(f"{target} cannot be written.")
    return errs


def _link_path(project_folder: Path, settings: Path):
    """location.json for a custom folder inside the same git repository as the project folder (teammates find it after
    a clone); None when it is outside (then only this computer's list knows it)."""
    repo = _git_root(project_folder)
    if repo and _inside(settings, repo) and settings != project_folder / DOT:
        return project_folder / DOT / LINK_FILE, os.path.relpath(settings, project_folder)
    return None, None


def create_project(name: str, location: str = "profile", project_folder=None, settings_dir=None, pid=None):
    """Create an empty project (project.json, .gitignore, link file, list entry). Returns (Project, errors)."""
    L = _lib()
    reg = load_registry()
    name = str(name or "").strip()
    base = L.slugify(pid or name) or "project"
    pid = _unique_id(reg, base)
    pf = None
    if project_folder:
        pf = _resolved(project_folder)
        if not pf.is_dir():
            return None, [f"project_folder {pf} is not an existing folder."]
    target, errs = _target(location, pid, pf, settings_dir)
    if errs:
        return None, errs
    errs = _target_errors(target)
    link, rel = (None, None)
    if location == "custom":
        if target == pf / DOT:
            location = "project"
        else:
            link, rel = _link_path(pf, target)
            if link and (link.parent / PROJECT_FILE).exists():
                errs.append(f"{link.parent} already holds a project's settings.")
    if location == "project" and (target / LINK_FILE).exists():
        errs.append(f"{target / LINK_FILE} already points to another settings folder.")
    if errs:
        return None, errs
    if registry_error():
        return None, [registry_error()]
    made = [] if target.exists() else [target]
    try:
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        _write_json(target / PROJECT_FILE, {"id": pid, "name": name or pid, "settings_format": SETTINGS_FORMAT})
        made.append(target / PROJECT_FILE)
        if location in ("project", "custom") and not (target / ".gitignore").exists():
            L._write_atomic(target / ".gitignore", GITIGNORE)
            made.append(target / ".gitignore")
        if link:
            _write_json(link, {"settings_dir": rel})
            made.append(link)
        entry = {"name": name or pid, "settings_dir": str(target), "location": location, "folders": _folders_for(pf),
                 "trusted": _now(), "created": _now()}
        reg["projects"][pid] = entry
        if not reg["default"] or reg["default"] not in reg["projects"]:
            reg["default"] = pid
        save_registry(reg)
    except OSError as ex:  # leave no half-made project behind
        for f in reversed(made):
            shutil.rmtree(f, ignore_errors=True) if f.is_dir() else f.unlink(missing_ok=True)
        return None, [f"Could not create the project in {target}: {ex}"]
    return _from_entry(pid, entry, "new"), []


def trust_project(project: Project) -> Project:
    """Remember a settings folder found in a project folder (after the user reviewed it) in this computer's list.
    A project whose folder was renamed or moved keeps its id (and so its sign-in): an entry with the same id whose
    settings folder no longer exists is pointed to the new place."""
    reg = load_registry()
    pid, entry = _entry_for_settings(reg, project.settings_dir)
    if not pid:
        old = reg["projects"].get(project.id)
        if isinstance(old, dict) and not (Path(old.get("settings_dir", "")) / PROJECT_FILE).is_file():
            pid, entry = project.id, old
            entry.update(settings_dir=str(project.settings_dir), location=project.location,
                         folders=_folders_for(project.project_folder))
        else:
            pid = _unique_id(reg, project.id)
            entry = {"name": project.name, "settings_dir": str(project.settings_dir), "location": project.location,
                     "folders": _folders_for(project.project_folder)}
    entry["trusted"] = _now()
    reg["projects"][pid] = entry
    reg["default"] = reg["default"] if reg["default"] in reg["projects"] else pid
    save_registry(reg)
    return _from_entry(pid, entry, project.found_by)


def set_machine_value(project: Project, key: str, value) -> bool:
    """A computer-specific value of a project (episodes_root, folders) in projects.json. False when the project is not
    in the list (settings named by VIDEO2AEO_PROJECT only)."""
    reg = load_registry()
    pid, entry = _entry_for_settings(reg, project.settings_dir)
    if not pid:
        return False
    if value in (None, ""):
        entry.pop(key, None)
    else:
        entry[key] = value
    reg["projects"][pid] = entry
    save_registry(reg)
    project.entry = entry
    return True


def _same_tree(a: Path, b: Path) -> bool:
    fa = sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file())
    fb = sorted(p.relative_to(b) for p in b.rglob("*") if p.is_file())
    return fa == fb and all((a / r).read_bytes() == (b / r).read_bytes() for r in fa)


def _link_points_to(link: Path, settings: Path) -> bool:
    target = _read_json(link).get("settings_dir")
    try:
        return isinstance(target, str) and (link.parent.parent / target).resolve() == settings.resolve()
    except (OSError, RuntimeError):
        return False


def move_project(pid: str, location: str, settings_dir=None, project_folder=None) -> dict:
    """Move a project's settings to another location: copy, verify, switch the list (and link file), then rename the
    old folder to <name>-moved-<timestamp> (never deleted). The target must be new or empty (or, for the project
    location, hold only this project's own link file). Any failure undoes the steps already done."""
    if registry_error():
        return {"ok": False, "errors": [registry_error()]}
    reg = load_registry()
    entry = reg["projects"].get(pid)
    if not isinstance(entry, dict) or not entry.get("settings_dir"):
        return {"ok": False, "errors": [f"Unknown project {pid!r}."], "projects": list_projects()}
    src = Path(entry["settings_dir"])
    if not (src / PROJECT_FILE).is_file():
        return {"ok": False, "errors": [f"The settings folder {src} is missing."]}
    pf = _resolved(project_folder) if project_folder else (Path(entry["folders"][0]) if entry.get("folders") else None)
    if pf is not None and not pf.is_dir():
        return {"ok": False, "errors": [f"project_folder {pf} is not an existing folder."]}
    target, errs = _target(location, pid, pf, settings_dir)
    if errs:
        return {"ok": False, "errors": errs}
    if location == "custom" and pf is not None and target == pf / DOT:
        location = "project"
    if target.resolve() == src.resolve():
        return {"ok": False, "errors": ["The settings are already in that folder."]}
    own_link = (pf / DOT / LINK_FILE) if pf else None
    own_link = own_link if own_link is not None and own_link.is_file() and _link_points_to(own_link, src) else None
    existing = sorted(f.name for f in target.iterdir()) if target.is_dir() else []
    if existing and not (location == "project" and own_link is not None and existing == [LINK_FILE]):
        return {"ok": False, "errors": [f"{target} is not empty ({', '.join(existing[:5])}); choose a new or empty folder."]}
    errs = [e for e in _target_errors(target) if "cannot be written" in e or "user folder" in e]
    link, rel = _link_path(pf, target) if (location == "custom" and pf) else (None, None)
    if link and link.exists() and link != own_link:
        errs.append(f"{link} already points to other settings.")
    if errs:
        return {"ok": False, "errors": errs}

    stamp = _stamp()
    undo: list = []   # steps to reverse, newest last
    tmp = target.parent / f".{target.name}.moving-{stamp}"
    moved = src.parent / f"{src.name}-moved-{stamp}"
    old_entry = json.loads(json.dumps(entry))
    try:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copytree(src, tmp, symlinks=True)
        undo.append(lambda: shutil.rmtree(tmp, ignore_errors=True))
        if not _same_tree(src, tmp):
            raise OSError("the copy differs from the original")
        if own_link is not None and location != "custom":  # this project's pointer is no longer needed
            link_text = own_link.read_text(encoding="utf-8")
            own_link.unlink()
            undo.append(lambda: _lib()._write_atomic(own_link, link_text))
        if target.is_dir():  # empty (or held only the retired link file)
            target.rmdir()
            undo.append(lambda: target.mkdir(mode=0o700, exist_ok=True))
        os.replace(tmp, target)
        undo.append(lambda: os.replace(target, tmp))
        if location in ("project", "custom") and not (target / ".gitignore").exists():
            _lib()._write_atomic(target / ".gitignore", GITIGNORE)
        entry.update(settings_dir=str(target.resolve()), location=location)
        if pf and str(pf) not in (entry.get("folders") or []):
            entry["folders"] = [*_folders_for(pf), *(entry.get("folders") or [])]
        reg["projects"][pid] = entry
        save_registry(reg)
        undo.append(lambda: (reg["projects"].__setitem__(pid, old_entry), save_registry(reg)))
        os.replace(src, moved)   # the old folder must not be found any more (a .video2aeo/ above a session folder)
        undo.append(lambda: os.replace(moved, src))
        if link:
            _write_json(link, {"settings_dir": rel})
    except OSError as ex:
        failed = []
        for step in reversed(undo):
            try:
                step()
            except OSError as uex:
                failed.append(str(uex))
        shutil.rmtree(tmp, ignore_errors=True)
        msg = f"Could not move the settings: {ex}."
        msg += (f" Nothing was changed; the settings are still in {src}." if not failed else
                f" Undoing it was incomplete ({'; '.join(failed)}) – check {src} and {target}.")
        return {"ok": False, "errors": [msg]}
    return {"ok": True, "project": _from_entry(pid, entry, "list").summary(), "old_folder": str(moved),
            **({"link_file": str(link)} if link else {})}


# ----------------------------------------------------------------------------
# one-time conversion of a 0.9 user folder
# ----------------------------------------------------------------------------

_MIGRATION: dict = {}   # per user folder: the result of this process's conversion (or its error)


def migration_info() -> dict:
    return _MIGRATION.get(str(user_home()), {})


def ensure_migrated() -> dict:
    """Convert a 0.9 user folder (flat brand.json, setup.json, …) into the first project, in the profile, once.
    Copy → verify → write projects.json; the old files stay where they are (a 0.9 install keeps working) and are not
    read again. On failure nothing is changed and the plugin reads the old folder in place (legacy)."""
    home = user_home()
    key = str(home)
    if key in _MIGRATION or (home / REGISTRY).exists() or not legacy_present(home):
        return _MIGRATION.get(key, {})
    lock = home / LOCK
    token = f"{os.getpid()}-{_now()}"
    for attempt in (1, 2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, token.encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                stale = (datetime.datetime.now().timestamp() - lock.stat().st_mtime) > 600
            except OSError:
                stale = True
            if not stale or attempt == 2:
                return {}   # another session is converting right now; read the old folder this time
            lock.unlink(missing_ok=True)   # a crashed conversion; try once more
        except OSError as ex:
            _MIGRATION[key] = {"error": f"Could not convert the settings in {home}: {ex}"}
            return _MIGRATION[key]
    tmp = dest_done = creds = None
    try:
        if (home / REGISTRY).exists():  # converted by another session meanwhile
            return {}
        L = _lib()
        cfg = _read_json(home / "config.json")
        brand = _read_json(home / "brand.json")
        name = str(brand.get("channel") or "").strip()
        pid = L.slugify(name) or "default"
        dest = home / "projects" / pid
        n = 1
        while dest.exists():
            n += 1
            dest = home / "projects" / f"{pid}-{n}"
        pid = dest.name
        tmp = home / "projects" / f".{pid}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(mode=0o700, parents=True)
        copied = []
        broken = [home / f"{n}.broken" for n in ("brand.json", "glossary.json", "setup.json")]  # never config.json's
        for f in [*(home / n for n in LEGACY_COPY), *broken]:
            if f.is_file():
                shutil.copy2(f, tmp / f.name)
                copied.append(f.name)
        for d in [home / "guidelines", *sorted(home.glob("backup-*"))]:
            if d.is_dir():
                shutil.copytree(d, tmp / d.name, symlinks=False)
                copied.append(d.name + "/")
        meta = {"id": pid, "name": name or pid, "settings_format": SETTINGS_FORMAT}
        if isinstance(cfg.get("models"), dict) and cfg["models"]:
            meta["models"] = cfg["models"]
        _write_json(tmp / PROJECT_FILE, meta)
        for c in copied:  # verify: byte-identical copies
            a, b = home / c.rstrip("/"), tmp / c.rstrip("/")
            if (a.is_dir() and not _same_tree(a, b)) or (a.is_file() and a.read_bytes() != b.read_bytes()):
                raise OSError(f"the copy of {c} differs from the original")
        if isinstance(cfg.get("wordpress"), dict) and cfg["wordpress"]:
            creds = home / "credentials" / f"{pid}.json"
            _write_json(creds, {"wordpress": cfg["wordpress"]}, mode=0o600)
        os.replace(tmp, dest)
        tmp, dest_done = None, dest
        root = cfg.get("episodes_root") if isinstance(cfg.get("episodes_root"), str) else ""
        entry = {"name": name or pid, "settings_dir": str(dest.resolve()), "location": "profile",
                 "folders": [root] if root else [], "trusted": _now(), "created": _now(),
                 "migrated": {"from": "0.9", "at": _now(), "old_files": str(home), "notice": True}}
        if root:
            entry["episodes_root"] = root
        save_registry({"version": 1, "default": pid, "projects": {pid: entry}})
        dest_done = creds = None   # converted: from here on nothing is rolled back
        try:
            L._write_atomic(home / MOVED_NOTE, (
                "Video2AEO 0.10 keeps every project in its own settings folder.\n"
                f"These settings were copied on {_now()} into the project '{name or pid}':\n  {dest}\n\n"
                "The files in this folder (brand.json, glossary.json, guidelines.md, setup.json, config.json, ...) are "
                "left as they were, so an older Video2AEO (0.9) still works with them. The new version does not read "
                "them any more: change the settings with /video2aeo:setup. WordPress sign-in details were copied to "
                f"credentials/{pid}.json; YouTube cookie settings stay in config.json.\n"))
        except OSError:
            pass
        _MIGRATION[key] = {"from": "0.9", "project": pid, "settings_dir": str(dest), "old_files": str(home),
                           "copied": copied}
        return _MIGRATION[key]
    except (OSError, ValueError) as ex:
        for leftover in (tmp, dest_done):  # nothing half-made stays behind; the next start tries again
            if leftover is not None:
                shutil.rmtree(leftover, ignore_errors=True)
        if creds is not None and not (home / REGISTRY).exists():
            creds.unlink(missing_ok=True)
        _MIGRATION[key] = {"error": f"Could not convert the settings in {home}: {ex}. They are used as they are."}
        return _MIGRATION[key]
    finally:
        try:
            if lock.read_text() == token:   # only the lock this process took
                lock.unlink()
        except OSError:
            pass


def clear_migration_notice(project: Project) -> None:
    reg = load_registry()
    pid, entry = _entry_for_settings(reg, project.settings_dir)
    if pid and isinstance(entry.get("migrated"), dict) and entry["migrated"].get("notice"):
        entry["migrated"]["notice"] = False
        reg["projects"][pid] = entry
        save_registry(reg)
        project.entry = entry


def migration_notice(project) -> dict | None:
    if project is None or project.legacy:
        return None
    m = project.entry.get("migrated")
    return {k: v for k, v in m.items() if k != "notice"} if isinstance(m, dict) and m.get("notice") else None
