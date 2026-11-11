"""
Setup-side helpers of video2aeo (stdlib only): what the computer has (check_environment), the optional subtitle
packages and their pip install, and the setup archive colleagues share (export_setup, read_setup_bundle).

Used by server/server.py (local MCP tools), scripts/aeo_net.py and scripts/aeo.py.
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import os
import platform
import re
import shlex
import sys
import zipfile
import zlib
from pathlib import Path

import aeo_lib as L


SUBTITLE_PACKAGES = {"youtube_transcript_api": "youtube-transcript-api", "yt_dlp": "yt-dlp"}


def missing_subtitle_packages() -> list:
    """pip names of the subtitle packages this interpreter cannot import."""
    return [pkg for mod, pkg in SUBTITLE_PACKAGES.items() if importlib.util.find_spec(mod) is None]


def pip_install_args(packages: list) -> list:
    """pip arguments for the interpreter running this helper (the one the plugin really uses).
    `--user` outside a virtualenv so no admin rights are needed; inside one it would be refused."""
    in_venv = getattr(sys, "base_prefix", sys.prefix) != sys.prefix
    return [sys.executable, "-m", "pip", "install", "--upgrade", *([] if in_venv else ["--user"]), *packages]


def externally_managed() -> bool:
    """PEP 668: Homebrew and Linux distribution Pythons refuse every pip install, `--user` included."""
    import sysconfig
    in_venv = getattr(sys, "base_prefix", sys.prefix) != sys.prefix
    return not in_venv and Path(sysconfig.get_path("stdlib"), "EXTERNALLY-MANAGED").exists()


def pip_install_command(packages: list) -> str:
    """The same command as a copy-paste line for the manual fallback (PowerShell on Windows, sh elsewhere).
    Where pip is refused (externally managed Python) it is the system package manager's yt-dlp instead."""
    if externally_managed():
        return "brew install yt-dlp" if sys.platform == "darwin" else "pipx install yt-dlp"
    a = pip_install_args(packages)
    if os.name == "nt":
        return f'& "{a[0]}" ' + " ".join(a[1:])   # PowerShell needs the call operator before a quoted path
    return " ".join(shlex.quote(x) for x in a)


def check_environment() -> dict:
    """What the plugin needs on this computer. Runs inside the interpreter that the desktop app launches.
    Read-only: checks that the settings folder (or its nearest existing parent) is writable without creating it."""
    py_ok = sys.version_info >= (3, 9)
    writable = L.user_dir_writable()
    missing = missing_subtitle_packages()
    problems = []
    if not py_ok:
        problems.append(f"Python {platform.python_version()} is too old – 3.9 or newer is needed.")
    if not writable:
        problems.append(f"The folder {L.PR.user_home()} cannot be written – settings cannot be saved.")
    return {
        "ok": not problems,
        "problems": problems,
        "python": {"version": platform.python_version(), "executable": sys.executable, "ok": py_ok},
        "user_dir": str(L.PR.user_home()),
        "user_dir_writable": writable,
        # Packages the subtitle download still lacks; the `install_subtitle_tools` tool installs them for the user.
        "missing_subtitle_tools": missing,
        "install_command": pip_install_command(missing) if missing else "",
    }


# --- setup archive: what a configured colleague shares, and what setup imports ------------------------------------
# Only these names are read or written; credentials (config.json wordpress/youtube) and the episodes folder never are.
ARCHIVE_MANIFEST = "video2aeo-setup.json"
ARCHIVE_FORMAT = 1
ARCHIVE_TOP_FILES = ("brand.json", "glossary.json", "guidelines.md")
ARCHIVE_MAX_FILE = 2_000_000      # bytes per file
ARCHIVE_MAX_TOTAL = 10_000_000    # bytes for the whole archive, uncompressed
ARCHIVE_MAX_MEMBERS = 200
SECRET_KEY_RE = re.compile(r"pass(word)?|token|secret|cookie|api[_-]?key", re.I)


def _archive_name(rel: str) -> str | None:
    """The archive name a relative member path stands for, or None when it is not part of a setup archive."""
    parts = rel.split("/")
    if len(parts) == 1 and parts[0] in (*ARCHIVE_TOP_FILES, ARCHIVE_MANIFEST, L.SETUP_FILE, "config.json"):
        return parts[0]
    if len(parts) == 2 and parts[0] == "guidelines" and L.GUIDELINE_FILE_RE.match(parts[1]):
        return rel
    return None


def _read_zip(src: Path) -> dict:
    """{archive name: bytes} from a .zip, read in memory (nothing is extracted). Hostile members – absolute or '..'
    paths, symlinks, too many or too large entries – reject the whole archive. A single wrapping folder (as Finder or
    Explorer make it) and __MACOSX entries are allowed."""
    with zipfile.ZipFile(src) as z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        if len(infos) > ARCHIVE_MAX_MEMBERS:
            raise ValueError(f"the archive has {len(infos)} files – too many for a setup archive.")
        names = []
        for i in infos:
            n = i.filename.replace("\\", "/")
            if n.startswith("/") or re.match(r"^[A-Za-z]:", n) or ".." in n.split("/"):
                raise ValueError(f"unsafe file name in the archive: {i.filename!r}.")
            if (i.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"the archive contains a link ({i.filename!r}); links are not accepted.")
            if not n.startswith("__MACOSX/"):
                names.append((n, i))
        roots = {n.rsplit("/", 1)[0] if "/" in n else "" for n, _ in names
                 if n.rsplit("/", 1)[-1] in (ARCHIVE_MANIFEST, "brand.json")}
        root = min(roots, key=len) if roots else ""
        found, total = {}, 0
        for n, i in names:
            if root and not n.startswith(root + "/"):
                continue
            name = _archive_name(n[len(root) + 1:] if root else n)
            if not name or name in found:
                continue
            with z.open(i) as f:
                data = f.read(ARCHIVE_MAX_FILE + 1)
            total += len(data)
            if len(data) > ARCHIVE_MAX_FILE or total > ARCHIVE_MAX_TOTAL:
                raise ValueError(f"{name} is too large for a setup archive.")
            found[name] = data
        return found


def _read_folder(src: Path) -> dict:
    """{archive name: bytes} from a folder: an unpacked archive, or the settings folder of an earlier install."""
    root = src / ".video2aeo" if not (src / "brand.json").is_file() and (src / ".video2aeo").is_dir() else src
    cands = [root / n for n in (*ARCHIVE_TOP_FILES, ARCHIVE_MANIFEST, L.SETUP_FILE, "config.json")]
    if (root / "guidelines").is_dir():
        cands += sorted((root / "guidelines").glob("*.md"))
    found, total = {}, 0
    for f in cands:
        if not f.is_file() or f.is_symlink():
            continue
        name = _archive_name(f.relative_to(root).as_posix())
        if not name:
            continue
        size = f.stat().st_size
        total += size
        if size > ARCHIVE_MAX_FILE or total > ARCHIVE_MAX_TOTAL:
            raise ValueError(f"{name} is too large for a setup archive.")
        found[name] = f.read_bytes()
    return found


def _clean_models(models) -> tuple[dict, list]:
    """Keep the parts of a models section this plugin version understands; return (models, dropped descriptions)."""
    table = L.load_json(L.PLUGIN_ROOT / "config" / "models.json")
    if not isinstance(models, dict):
        return {}, ["models (not an object)"] if models not in (None, {}) else []
    out = {}
    dropped = [f"models.{k}" for k in sorted(set(models) - {"profile", "overrides"})]
    if "overrides" in models and not isinstance(models["overrides"], dict):
        dropped.append("models.overrides (not an object)")
    if models.get("profile") not in (None, ""):
        if L._models_errors({"profile": models["profile"]}, table):
            dropped.append(f"models.profile {models['profile']!r}")
        else:
            out["profile"] = models["profile"]
    ov = models.get("overrides") if isinstance(models.get("overrides"), dict) else {}
    for op, m in ov.items():
        if L._models_errors({"overrides": {op: m}}, table):
            dropped.append(f"models.overrides.{op} {m!r}")
        else:
            out.setdefault("overrides", {})[op] = m
    return out, dropped


def read_setup_bundle(path: str) -> dict:
    """Read a colleague's setup archive (.zip from export_setup, or a folder – also the settings folder of an earlier
    install) for review. Read-only; the content is untrusted: setup shows it to the user before save_setup.
    Returns brand, glossary, guidelines_md, guidelines_files, guidelines_off, models (only the parts this version
    understands; the rest is listed under `dropped`), warnings, unrecognised_keys."""
    raw = L.native_path(path)
    if not raw:
        return {"ok": False, "errors": ["Give the path of the setup .zip or folder."]}
    src = Path(raw).expanduser()
    try:
        if not src.exists():
            return {"ok": False, "errors": [f"{src} does not exist."]}
        if src.is_dir():
            files = _read_folder(src)
        elif zipfile.is_zipfile(src):
            files = _read_zip(src)
        else:
            return {"ok": False, "errors": [f"{src} is neither a folder nor a .zip file."]}
        text = {n: b.decode("utf-8-sig") for n, b in files.items()}

        def obj(name):
            data = json.loads(text[name])
            if not isinstance(data, dict):
                raise ValueError(f"{name} must hold a JSON object.")
            return data

        out: dict = {"ok": True, "source": str(src), "found": sorted(n for n in text if n not in ("config.json", L.SETUP_FILE)),
                     "warnings": [], "dropped": []}
        for name in ("brand.json", "glossary.json"):
            if name in text:
                out[name[:-5]] = obj(name)
        if text.get("guidelines.md", "").strip():
            out["guidelines_md"] = text["guidelines.md"]
        guides = {n.split("/", 1)[1]: v for n, v in text.items() if n.startswith("guidelines/")}
        if guides:
            out["guidelines_files"] = guides
        team: dict = {}
        if ARCHIVE_MANIFEST in text:
            team = obj(ARCHIVE_MANIFEST)
            out["archive_format"], out["plugin_version"] = team.get("archive_format"), team.get("plugin_version", "")
            out["exported"] = team.get("exported", "")
            if not isinstance(out["archive_format"], int):
                out["warnings"].append("The archive does not say which format it uses; check the imported values carefully.")
            elif out["archive_format"] > ARCHIVE_FORMAT:
                out["warnings"].append(f"The archive was made by a newer video2aeo ({out['plugin_version'] or 'unknown'}); "
                                       "update the plugin, or check the imported values carefully.")
        else:  # an earlier install's settings folder: its setup.json and the models of its config.json
            if L.SETUP_FILE in text:
                team["guidelines_off"] = obj(L.SETUP_FILE).get("guidelines_off", [])
            if "config.json" in text:
                cfg = obj("config.json")
                if "models" in cfg:
                    team["models"] = cfg["models"]
                if cfg.get("wordpress") or cfg.get("youtube"):
                    out["warnings"].append("WordPress and YouTube sign-in details in config.json were NOT imported; "
                                           "they stay on that computer.")
        if "guidelines_off" in team:
            ids = [str(i) for i in team["guidelines_off"]] if isinstance(team["guidelines_off"], list) else []
            out["guidelines_off"] = sorted(set(i for i in ids if i in L.ADJUSTABLE_GUIDELINES))
            out["dropped"] += [f"guidelines_off {i!r}" for i in sorted(set(ids) - set(L.ADJUSTABLE_GUIDELINES))]
        if "models" in team:
            out["models"], dropped = _clean_models(team["models"])
            out["dropped"] += dropped
        if "brand" in out:
            out["unrecognised_keys"] = L.unrecognised_keys(L.expand_dotted(out["brand"]),
                                                           L.load_json(L.PLUGIN_ROOT / "config" / "brand.json"))
        else:
            out["ok"] = False
            out["errors"] = [f"No brand.json found in {src} – this is not a video2aeo setup."]
        return out
    # The archive is untrusted input: damaged compression, encrypted members or odd JSON must end in a message.
    except (OSError, ValueError, TypeError, AttributeError, KeyError, EOFError, zlib.error, zipfile.BadZipFile,
            RuntimeError, NotImplementedError) as ex:
        return {"ok": False, "errors": [f"Could not read {src}: {ex}"]}


def _secret_warnings(texts: dict) -> list:
    """Things in the files about to be shared that look like credentials: credential-like key names, or the
    WordPress application password of config.json (the site address and user name are not secret)."""
    project = L.PR.active()
    wp = project.credentials().get("wordpress") if project else None
    password = wp.get("app_password") if isinstance(wp, dict) else None
    out = []
    for name, body in texts.items():
        if isinstance(password, str) and len(password) >= 6 and password in body:
            out.append(f"{name} contains the WordPress application password from config.json.")
        if name.endswith(".json"):
            keys = re.findall(r'"([^"]+)"\s*:', body)
            hits = sorted({k for k in keys if SECRET_KEY_RE.search(k)})
            if hits:
                out.append(f"{name} has keys that look like credentials: {hits}.")
    return out


def export_setup(out_dir: str) -> dict:
    """Write this computer's team setup to one .zip in out_dir for colleagues to import: brand (incl. formats),
    glossary, guidelines.md, guidelines/*.md, switched-off guidelines and model choices. Never config.json's sign-in
    details or the episodes folder. Never overwrites a file."""
    st = L.setup_status()
    if not st["configured"]:
        return {"ok": False, "errors": ["Setup is not complete on this computer yet – nothing to share."]}
    dest = Path(L.native_path(out_dir)).expanduser()
    if not dest.is_absolute() or not dest.is_dir() or dest.is_symlink() or not os.access(dest, os.W_OK):
        return {"ok": False, "errors": [f"{dest} must be an existing, writable folder (absolute path)."]}
    try:
        sd = L.settings_dir()
        texts = {n: (sd / n).read_text(encoding="utf-8") for n in ARCHIVE_TOP_FILES if (sd / n).is_file()}
        gdir = sd / "guidelines"
        for f in sorted(gdir.glob("*.md")) if gdir.is_dir() else []:
            if L.GUIDELINE_FILE_RE.match(f.name) and not f.is_symlink():
                texts[f"guidelines/{f.name}"] = f.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as ex:
        return {"ok": False, "errors": [f"Could not read the settings in {L.settings_dir()}: {ex}"]}
    manifest = {"archive_format": ARCHIVE_FORMAT,
                "plugin_version": L.load_json(L.PLUGIN_ROOT / ".claude-plugin" / "plugin.json").get("version", ""),
                "exported": datetime.date.today().isoformat(),
                "guidelines_off": st["guidelines_off"]}
    models = L.team_config().get("models")
    if isinstance(models, dict) and models:
        manifest["models"] = models
    texts[ARCHIVE_MANIFEST] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    slug = L.slugify(st["current"].get("channel", "")) or "team"
    base = f"video2aeo-setup-{slug}-{manifest['exported']}"
    for n in range(1, 100):
        target = dest / (f"{base}.zip" if n == 1 else f"{base}-{n}.zip")
        try:
            fh = open(target, "xb")
        except FileExistsError:
            continue
        except OSError as ex:
            return {"ok": False, "errors": [f"Could not write {target}: {ex}"]}
        try:
            with fh, zipfile.ZipFile(fh, "w", zipfile.ZIP_DEFLATED) as z:
                for name, body in sorted(texts.items()):
                    z.writestr(name, body)
        except OSError as ex:
            target.unlink(missing_ok=True)
            return {"ok": False, "errors": [f"Could not write {target}: {ex}"]}
        return {"ok": True, "path": str(target), "included": sorted(texts),
                "left_out": ["config.json: WordPress password, YouTube cookies and the episodes folder stay on this computer",
                             "backups and damaged copies"],
                "warnings": _secret_warnings(texts)}
    return {"ok": False, "errors": [f"Too many setup archives named {base}* in {dest}."]}
