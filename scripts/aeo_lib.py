"""
video2aeo core library (stdlib only).

Deterministic parts of the pipeline – the LLM never does these:
  * transcript parsing (YouTube "MM:SS text" paste, VTT, SRT, JSON segments)
  * rendering episode.json -> youtube-description.txt, article.wp.html (+ schema.jsonld, wp-post-fields.json)
    – each output independently, so a command can render only its own file
  * validation (YouTube limits, chapter rules, Gutenberg block balance, FAQ parity, placeholders)

Episode folder layout: the paste-ready outputs sit in the folder itself, everything else (episode.json, transcripts,
schema, review sheet, push state) lives in its `work/` subfolder. Older flat folders are still read.

Used by scripts/aeo.py (CLI) and server/server.py (local MCP tools).
"""
from __future__ import annotations

import datetime
import html
import importlib.util
import json
import os
import platform
import re
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
# Per-user brand, glossary and credentials – never in the plugin. VIDEO2AEO_HOME overrides it (used by the example checks).
# Legacy: before 0.4.0 the plugin was called yt-aeo – keep using its folder/variable if the new ones do not exist.
def _user_dir() -> Path:
    env = os.environ.get("VIDEO2AEO_HOME") or os.environ.get("YT_AEO_HOME")
    if env:
        return Path(env).expanduser()
    new, old = Path.home() / ".video2aeo", Path.home() / ".yt-aeo"
    return old if (old.is_dir() and not new.exists()) else new


USER_DIR = _user_dir()
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")
GENERIC_CHAPTERS = {
    "интро", "въведение", "начало", "разговор", "пазар", "съвети", "финал",
    "край", "заключение", "intro", "outro", "end", "start", "q&a", "въпроси",
}
YT_DESCRIPTION_LIMIT = 5000
YT_DESCRIPTION_MARGIN = 100
CHAPTER_TITLE_MAX = 70

WORK_DIR = "work"
OUTPUT_FILES = {"youtube": "youtube-description.txt", "wordpress": "article.wp.html"}
# Alternative description layouts are written next to the default file and never replace it.
DESCRIPTION_LAYOUT_FILES = {"classic": "youtube-description.txt", "merged": "youtube-description.merged.txt"}
OUTPUT_ORDER = ("youtube", "wordpress")

# ----------------------------------------------------------------------------
# config
# ----------------------------------------------------------------------------

def load_json(path: Path | str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def work_dir(ep_dir: Path) -> Path:
    """The folder for working files (created on demand by the writers)."""
    return Path(ep_dir) / WORK_DIR


def work_file(ep_dir: Path, name: str) -> Path:
    """Where to write a working file: <episode>/work/<name>."""
    d = work_dir(ep_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def find_work_file(ep_dir: Path, name: str) -> Path:
    """Where to read a working file: work/ first, then the episode folder itself (older flat layout)."""
    for base in (work_dir(ep_dir), Path(ep_dir)):
        if (base / name).exists():
            return base / name
    return work_dir(ep_dir) / name


def load_episode(ep_dir: Path) -> dict:
    return load_json(find_work_file(ep_dir, "episode.json"))


def load_brand(override: Path | None = None) -> dict:
    """Generic plugin defaults, merged with ~/.video2aeo/brand.json and then an explicit override file."""
    brand = load_json(PLUGIN_ROOT / "config" / "brand.json")
    for path in (USER_DIR / "brand.json", override):
        if path and Path(path).exists():
            brand = _deep_merge(brand, load_json(path))
    return brand


SETUP_FILE = "setup.json"
# Placeholders the user must fill; optional ones are blanked by save_setup when skipped.
REQUIRED_FIELDS = (("channel",), ("topics",))
OPTIONAL_FIELDS = (("organization", "name"), ("organization", "logo"), ("description", "schedule"),
                   ("description", "disclaimer_url"), ("description", "social_links"))
# Ids of the adjustable guidelines in skills/setup/references/guideline-catalog.md (dev/smoke.py checks they match).
ADJUSTABLE_GUIDELINES = ("answer-first", "question-titles", "knowledge-chapters", "question-index", "freshness-note",
                         "euro-equivalents", "skip-sponsor-reads", "question-sections", "faq-and-authors")
PROMO_POSITIONS = ("end", "top")
# Episode format (setup step 4): allowed values of the enumerated brand.format fields.
FORMAT_ENUMS = {"speakers": ("solo", "host_and_guest", "host_and_guests", "panel", "varies"),
                "opening_teaser": ("none", "sometimes", "always")}


def resolve_format(brand: dict, profile: str | None = None) -> dict:
    """The episode format to use: the brand's base `format`, overridden by the named profile in `formats`
    (a channel may have several shows/formats). Unknown or empty profile -> the base format."""
    base = brand.get("format") or {}
    prof = (brand.get("formats") or {}).get(profile or "")
    return _deep_merge(base, prof) if isinstance(prof, dict) else dict(base)


def _format_errors(fmt, where: str) -> list:
    errors = []
    if not isinstance(fmt, dict):
        return [f"{where} must be an object."]
    for key, allowed in FORMAT_ENUMS.items():
        if key in fmt and fmt[key] not in allowed:
            errors.append(f"{where}.{key} must be one of {allowed}.")
    for key in ("recurring_segments", "intro_outro", "notes"):
        if key in fmt and not isinstance(fmt[key], str):
            errors.append(f"{where}.{key} must be text.")
    links = fmt.get("links", [])
    if not isinstance(links, list) or any(not isinstance(u, str) or not re.match(r"https?://\S+$", u) for u in links):
        errors.append(f"{where}.links must be a list of http(s) addresses.")
    cov = fmt.get("coverage") or {}
    if not isinstance(cov, dict):
        return errors + [f"{where}.coverage must be an object."]
    nums = [cov[k] for k in ("full_until_minutes", "selective_from_minutes", "max_questions_selective") if k in cov]
    nums += [fmt["teaser_max_minutes"]] if "teaser_max_minutes" in fmt else []
    if any(isinstance(n, bool) or not isinstance(n, (int, float)) or n <= 0 for n in nums):
        errors.append(f"{where}.coverage values and teaser_max_minutes must be positive numbers.")
    elif {"full_until_minutes", "selective_from_minutes"} <= set(cov) and \
            cov["full_until_minutes"] >= cov["selective_from_minutes"]:
        errors.append(f"{where}.coverage.full_until_minutes must be smaller than selective_from_minutes.")
    return errors


def coverage_plan(duration_seconds: float, fmt: dict | None = None) -> dict:
    """How much of an episode the knowledge map should cover, by its length. Short episodes are covered fully, long
    ones selectively (only the most important questions, minor stretches folded into neighbouring chapters)."""
    fmt = fmt or {}
    cov = {**{"full_until_minutes": 30, "selective_from_minutes": 75, "max_questions_selective": 10},
           **(fmt.get("coverage") or {})}
    minutes = round((duration_seconds or 0) / 60, 1)
    if minutes <= 0:
        return {"tier": "unknown", "minutes": 0, "rule": "Length unknown – use the balanced rule (6–8 questions)."}
    if minutes <= cov["full_until_minutes"]:
        return {"tier": "full", "minutes": minutes, "questions": [4, 10],
                "rule": "Short episode: cover every distinct topic – a question and a chapter for each; nothing is dropped."}
    if minutes < cov["selective_from_minutes"]:
        return {"tier": "balanced", "minutes": minutes, "questions": [6, 8],
                "rule": "Medium episode: 6–8 questions people actually ask; every topic of 2+ minutes gets a chapter."}
    top = int(cov["max_questions_selective"])
    return {"tier": "selective", "minutes": minutes, "questions": [6, top],
            "rule": f"Long episode: keep only the most important questions (at most {top}), ranked by how likely people ask "
                    "an AI or search about them. Minor topics get no question of their own – fold them into the nearest "
                    "chapter. Chapters still span the whole timeline (about one per 5–10 minutes)."}


def require_setup():
    """Hard gate for the tools that produce output: None when setup is done, else an error dict that tells the
    caller to run the `setup` skill first. Prompt instructions alone are skippable – this is not."""
    st = setup_status()
    if st["configured"]:
        return None
    return {"ok": False, "setup_required": True,
            "error": "Setup is not done on this computer yet. STOP: do not continue with the user's request. "
                     "Run the `setup` skill (/video2aeo:setup) first, then retry this step.",
            "missing": st["missing"], "unreadable": st["unreadable"], "user_dir": st["user_dir"]}


def _get(d: dict, path: tuple):
    for k in path:
        d = d.get(k) if isinstance(d, dict) else None
    return d


def _set(d: dict, path: tuple, value) -> None:
    for k in path[:-1]:
        d = d.setdefault(k, {})
    d[path[-1]] = value


def _write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def setup_status() -> dict:
    """Has the one-time brand setup been done? Used by every user-facing skill as its preflight check.
    Never raises on a damaged file – it reports it under `unreadable` so setup can repair it."""
    unreadable = []
    try:
        brand = load_brand()
    except (OSError, ValueError) as ex:
        unreadable.append(f"brand.json: {ex}")
        brand = load_json(PLUGIN_ROOT / "config" / "brand.json")
    marker = USER_DIR / SETUP_FILE
    info = {}
    if marker.exists():
        try:
            info = load_json(marker)
        except (OSError, ValueError) as ex:
            unreadable.append(f"{SETUP_FILE}: {ex}")
    guidelines_path = USER_DIR / "guidelines.md"
    try:
        guidelines_md = guidelines_path.read_text(encoding="utf-8") if guidelines_path.exists() else ""
    except OSError as ex:
        unreadable.append(f"guidelines.md: {ex}")
        guidelines_md = ""
    missing = sorted(set(PLACEHOLDER_RE.findall(json.dumps(brand, ensure_ascii=False))))
    required_missing = [".".join(p) for p in REQUIRED_FIELDS
                        if not str(_get(brand, p) or "").strip() or PLACEHOLDER_RE.search(str(_get(brand, p)))]
    d = brand["description"]
    warnings = []
    if "example.com" in brand.get("site", {}).get("base_url", ""):
        warnings.append("site.base_url is still example.com – article links in the description will point there.")
    if d.get("promo_position", "end") not in PROMO_POSITIONS:
        warnings.append(f"description.promo_position must be one of {PROMO_POSITIONS}.")
    legacy_footer = "{PROMO}" not in d.get("footer", "") and "{{PROMO_BLOCK}}" not in d.get("footer", "")
    done = bool(info.get("completed"))
    try:
        gl = load_json(USER_DIR / "glossary.json") if (USER_DIR / "glossary.json").exists() else {}
    except (OSError, ValueError):
        gl = {}
    glossary_entries = sum(len(gl.get(k) or []) for k in ("fixes", "names", "sponsor_read_markers"))
    if not glossary_entries:
        warnings.append("The brand glossary is empty – ask for brand, people and product names, common caption "
                        "mistakes and sponsor-read markers (setup step 3).")
    return {
        "configured": done and not missing and not unreadable,
        "setup_completed": done,
        "user_dir": str(USER_DIR),
        "missing": missing,
        "required_missing": required_missing,
        "unreadable": unreadable,
        "warnings": warnings,
        "legacy_footer": legacy_footer,
        "glossary_entries": glossary_entries,
        "current": {
            "language": brand.get("language", "bg"),
            "language_name": brand.get("language_name", ""),
            "channel": brand.get("channel", ""),
            "topics": brand.get("topics", ""),
            "site": brand.get("site", {}),
            "organization": brand.get("organization", {}),
            "header": d.get("header", ""),
            "promo": d.get("promo", ""),
            "promo_position": d.get("promo_position", "end"),
            "schedule": d.get("schedule", ""),
            "disclaimer_url": d.get("disclaimer_url", ""),
            "social_links": d.get("social_links", ""),
            "footer": d.get("footer", ""),
            "format": brand.get("format", {}),
            "formats": brand.get("formats", {}),
            "guidelines_md": guidelines_md,
        },
        "guidelines_off": info.get("guidelines_off", []),
    }


def check_environment() -> dict:
    """What the plugin needs on this computer. Runs inside the interpreter that the desktop app launches.
    Read-only: checks that the settings folder (or its nearest existing parent) is writable without creating it."""
    py_ok = sys.version_info >= (3, 9)
    probe = USER_DIR
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    writable = os.access(probe, os.W_OK)
    optional = {
        "youtube_transcript_api": "automatic subtitle download",
        "yt_dlp": "subtitle download, second route",
    }
    optional_status = {m: importlib.util.find_spec(m) is not None for m in optional}
    problems = []
    if not py_ok:
        problems.append(f"Python {platform.python_version()} is too old – 3.9 or newer is needed.")
    if not writable:
        problems.append(f"The folder {USER_DIR} cannot be written – brand settings cannot be saved.")
    return {
        "ok": not problems,
        "problems": problems,
        "python": {"version": platform.python_version(), "executable": sys.executable, "ok": py_ok},
        "platform": f"{platform.system()} {platform.release()}",
        "user_dir": str(USER_DIR),
        "user_dir_writable": writable,
        "optional": {m: {"installed": optional_status[m], "enables": optional[m]} for m in optional},
        "automatic_subtitles": any(optional_status.values()),
    }


def _expand_dotted(d: dict) -> dict:
    """{"description.promo": x} -> {"description": {"promo": x}} (agents often send dotted keys)."""
    out: dict = {}
    for k, v in d.items():
        v = _expand_dotted(v) if isinstance(v, dict) else v
        path = tuple(k.split("."))
        cur = _get(out, path)
        _set(out, path, _deep_merge(cur, v) if isinstance(cur, dict) and isinstance(v, dict) else v)
    return out


def save_setup(brand: dict | None = None, glossary: dict | None = None, guidelines_md: str | None = None,
               guidelines_off: list | None = None) -> dict:
    """Write the user's brand files to USER_DIR (fixed file names only).
    brand/glossary are merged over any existing file; omitted arguments keep what is saved.
    Skipped optional fields are saved as empty text. Everything is validated before anything is written."""
    errors = []
    if brand is not None and not isinstance(brand, dict):
        errors.append("brand must be an object.")
    if glossary is not None and not isinstance(glossary, dict):
        errors.append("glossary must be an object.")
    if guidelines_md is not None and not isinstance(guidelines_md, str):
        errors.append("guidelines_md must be text.")
    if guidelines_off is not None:
        if not isinstance(guidelines_off, list):
            errors.append("guidelines_off must be a list of ids.")
        else:
            unknown = sorted(set(map(str, guidelines_off)) - set(ADJUSTABLE_GUIDELINES))
            if unknown:
                errors.append(f"Unknown or locked guideline ids: {unknown}. Adjustable ids: {list(ADJUSTABLE_GUIDELINES)}.")
    if brand is None and glossary is None and guidelines_md is None and guidelines_off is None:
        errors.append("Nothing to save.")
    brand = _expand_dotted(brand) if isinstance(brand, dict) else brand
    pos = _get(brand or {}, ("description", "promo_position"))
    if pos is not None and pos not in PROMO_POSITIONS:
        errors.append(f"description.promo_position must be one of {PROMO_POSITIONS}.")

    if _get(brand or {}, ("format",)) is not None:
        errors += _format_errors(brand["format"], "format")
    profiles = _get(brand or {}, ("formats",))
    if profiles is not None:
        if not isinstance(profiles, dict):
            errors.append("formats must be an object: profile id -> format.")
        else:
            for pid, prof in profiles.items():
                errors += _format_errors(prof, f"formats.{pid}")
                if isinstance(prof, dict) and not str(prof.get("label", "")).strip():
                    errors.append(f"formats.{pid}.label (a plain name the user recognises) is required.")

    if errors:
        return {"ok": False, "errors": errors, **setup_status()}

    def read_or_set_aside(path: Path) -> dict:
        """A damaged settings file is kept as <name>.broken and replaced, so setup can always repair the folder."""
        if not path.exists():
            return {}
        try:
            data = load_json(path)
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
        broken.append(path)
        return {}

    writes: dict = {}
    broken: list = []
    marker_path = USER_DIR / SETUP_FILE
    old_marker = read_or_set_aside(marker_path)
    for name, data in (("brand.json", brand), ("glossary.json", glossary)):
        path = USER_DIR / name
        if data is None and not (name == "brand.json" and path.exists()):
            continue
        merged = _deep_merge(read_or_set_aside(path), data or {})
        if name == "brand.json":
            full = _deep_merge(load_json(PLUGIN_ROOT / "config" / "brand.json"), merged)
            for p in OPTIONAL_FIELDS:
                v = _get(full, p)
                if v is None or PLACEHOLDER_RE.search(str(v)):
                    _set(merged, p, "")
        writes[path] = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"

    if guidelines_md is not None:
        writes[USER_DIR / "guidelines.md"] = guidelines_md.rstrip() + "\n"
    off = sorted(set(guidelines_off)) if guidelines_off is not None else old_marker.get("guidelines_off", [])
    writes[marker_path] = json.dumps({"completed": datetime.date.today().isoformat(), "guidelines_off": off},
                                     ensure_ascii=False, indent=2) + "\n"
    try:
        USER_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        for path in broken:
            os.replace(path, path.with_name(path.name + ".broken"))
        g = USER_DIR / "guidelines.md"
        if g in writes and g.exists() and g.read_text(encoding="utf-8") != writes[g]:
            _write_atomic(USER_DIR / "guidelines.md.bak", g.read_text(encoding="utf-8"))
        for path, text in writes.items():  # setup.json last: a failure never marks setup as done
            if path != marker_path:
                _write_atomic(path, text)
        _write_atomic(marker_path, writes[marker_path])
    except OSError as ex:
        return {"ok": False, "errors": [f"Could not write to {USER_DIR}: {ex}"], **setup_status()}
    return {"ok": True, "set_aside": [p.name + ".broken" for p in broken], **setup_status()}


def _deep_merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out

# ----------------------------------------------------------------------------
# time helpers
# ----------------------------------------------------------------------------

def parse_ts(s: str) -> float:
    """'01:02', '1:02:03', '00:01:02.500', '00:01:02,500' -> seconds."""
    s = s.strip().replace(",", ".")
    parts = s.split(":")
    secs = 0.0
    for p in parts:
        secs = secs * 60 + float(p)
    return secs


def fmt_ts(seconds: float, force_hours: bool = False) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h or force_hours:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def iso_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return "PT" + (f"{h}H" if h else "") + (f"{m}M" if m else "") + f"{s}S"

# ----------------------------------------------------------------------------
# transcript parsing
# ----------------------------------------------------------------------------

_LINE_TS = re.compile(r"^\s*(\d{1,2}:\d{2}(?::\d{2})?)\s+(.*\S)?\s*$")
_VTT_CUE = re.compile(r"(\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})\s*-->\s*(\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})")
_TAG = re.compile(r"<[^>]+>")


def parse_transcript_text(text: str) -> list[dict]:
    """Return [{'start': sec, 'text': str}] from VTT / SRT / YouTube copy-paste / JSON."""
    t = text.lstrip("﻿")
    stripped = t.strip()
    if stripped.startswith("[") or stripped.startswith("{"):
        data = json.loads(stripped)
        if isinstance(data, dict):
            data = data.get("segments") or data.get("snippets") or []
        return _dedupe([{"start": float(d.get("start", 0)), "text": str(d.get("text", "")).strip()} for d in data])
    if _VTT_CUE.search(t):
        return _parse_cues(t)
    segs = []
    for line in t.splitlines():
        m = _LINE_TS.match(line)
        if m and m.group(2):
            segs.append({"start": parse_ts(m.group(1)), "text": m.group(2).strip()})
    return _dedupe(segs)


def _parse_cues(t: str) -> list[dict]:
    segs, cur = [], None
    for line in t.splitlines():
        m = _VTT_CUE.search(line)
        if m:
            cur = {"start": parse_ts(m.group(1)), "lines": []}
            segs.append(cur)
            continue
        if cur is None:
            continue
        line = line.strip()
        if line and not line.isdigit():
            cur["lines"].append(html.unescape(_TAG.sub("", line)).strip())
    # YouTube auto-captions "roll": each cue repeats the previous cue's last line first.
    prev_last = None
    for s in segs:
        lines = [l for l in s["lines"] if l]
        if prev_last is not None and len(lines) > 1 and lines[0] == prev_last:
            lines = lines[1:]
        if lines:
            prev_last = lines[-1]
        s["lines"] = lines
    out = [{"start": s["start"], "text": " ".join(s["lines"]).strip()} for s in segs]
    return _dedupe([s for s in out if s["text"]])


def _dedupe(segs: list[dict]) -> list[dict]:
    """YouTube auto-captions repeat rolling lines; drop exact/prefix repeats."""
    out: list[dict] = []
    for s in segs:
        txt = s["text"]
        if not txt or txt in ("[музика]", "[Music]"):
            continue
        if out and (txt == out[-1]["text"] or out[-1]["text"].endswith(txt)):
            continue
        if out and txt.startswith(out[-1]["text"]):
            out[-1]["text"] = txt
            continue
        out.append({"start": round(s["start"], 2), "text": txt})
    return out


def segments_to_text(segs: list[dict], para_seconds: int = 30) -> str:
    """Group segments into ~30 s paragraphs with a [MM:SS] stamp – the raw reading copy."""
    lines, buf, start = [], [], None
    for s in segs:
        if s["text"].startswith(">>") and buf:  # speaker change in YouTube captions
            lines.append(f"[{fmt_ts(start)}] " + " ".join(buf))
            buf, start = [], None
        if start is None:
            start = s["start"]
        buf.append(s["text"])
        if s["start"] - start >= para_seconds:
            lines.append(f"[{fmt_ts(start)}] " + " ".join(buf))
            buf, start = [], None
    if buf:
        lines.append(f"[{fmt_ts(start or 0)}] " + " ".join(buf))
    return "\n\n".join(lines) + "\n"


def write_raw_transcript(segs: list[dict], out_dir: Path, source: str) -> dict:
    work_file(out_dir, "transcript.raw.json").write_text(
        json.dumps({"source": source, "segments": segs}, ensure_ascii=False, indent=1), encoding="utf-8")
    work_file(out_dir, "transcript.raw.txt").write_text(segments_to_text(segs), encoding="utf-8")
    dur = segs[-1]["start"] if segs else 0
    return {"segments": len(segs), "last_timestamp": fmt_ts(dur), "words": sum(len(s["text"].split()) for s in segs),
            "files": [f"{WORK_DIR}/transcript.raw.json", f"{WORK_DIR}/transcript.raw.txt"], "source": source}

# ----------------------------------------------------------------------------
# YouTube URL helpers
# ----------------------------------------------------------------------------

_ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})")


def video_id_from_url(url: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url.strip()):
        return url.strip()
    m = _ID_RE.search(url)
    if not m:
        raise ValueError(f"Cannot find a YouTube video id in: {url}")
    return m.group(1)


def watch_url(vid: str, t: float | None = None) -> str:
    base = f"https://www.youtube.com/watch?v={vid}"
    return base + (f"&t={int(t)}s" if t else "")

# ----------------------------------------------------------------------------
# rendering helpers
# ----------------------------------------------------------------------------

def esc(s: str) -> str:
    return html.escape(str(s), quote=False)


def inline_md(s: str) -> str:
    """Escape, then allow **bold**, *italic* and [text](url) in copy."""
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
    return s


def plain(s: str) -> str:
    """Strip our light markdown for plain-text targets (YouTube, JSON-LD)."""
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", str(s))
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1", s)
    return s.replace("<", "‹").replace(">", "›")


def article_url(ep: dict, brand: dict) -> str:
    site = brand["site"]
    return site["base_url"].rstrip("/") + "/" + site["kb_path"].strip("/") + "/" + ep["article"]["slug"].strip("/") + "/"

# ----------------------------------------------------------------------------
# 1) YouTube description
# ----------------------------------------------------------------------------

DESC_SEP = "_" * 39
FOOTER_FIELDS = {"{SCHEDULE}": "schedule", "{DISCLAIMER_URL}": "disclaimer_url", "{SOCIAL_LINKS}": "social_links"}


def _promo_and_footer(d: dict) -> tuple[str, str]:
    """Return (top_block, footer). Fills the footer's {SCHEDULE}/{DISCLAIMER_URL}/{SOCIAL_LINKS} tokens (a line whose
    value is empty is dropped) and places the promo (links, messages, ads) at {PROMO}, above the footer, or at the top."""
    lines = []
    for line in d["footer"].rstrip().replace("{{PROMO_BLOCK}}", "{PROMO}").split("\n"):
        for token, key in FOOTER_FIELDS.items():
            pattern = r"(?<!\{)" + re.escape(token) + r"(?!\})"  # not inside a literal {{…}} placeholder
            if line is not None and re.search(pattern, line):
                value = str(d.get(key) or "").strip()
                line = re.sub(pattern, lambda _m: value, line) if value else None
        if line is not None:
            lines.append(line)
    footer = "\n".join(lines)
    promo = (d.get("promo") or "").replace("{PROMO}", "").strip()
    if promo and d.get("promo_position") != "top":
        if "{PROMO}" in footer:
            return "", footer.replace("{PROMO}", promo)
        if promo in footer:  # older footer that already carries the promo text
            return "", footer
        return "", f"{promo}\n{DESC_SEP}\n{footer}"
    footer = re.sub(r"(_{10,}\n)\s*(?=_{10,})", "", footer.replace("{PROMO}", "")).strip()
    return promo, footer


def _qa_chapters(ep: dict) -> list[tuple[int, str, str | None]]:
    """Merged layout: one (t, line, answer) per chapter. A question is attached to the chapter that contains its
    `chapter_t` (the latest chapter starting at or before it); its text replaces the chapter title when it fits the
    YouTube chapter limit, otherwise the knowledge title stays and the answer still follows."""
    chapters = ep["chapters"]
    by_idx: dict[int, dict] = {}
    for q in ep.get("questions", []):
        t = q.get("chapter_t")
        if t is None:
            continue
        idx = max((i for i, c in enumerate(chapters) if c["t"] <= t), default=0)
        by_idx.setdefault(idx, q)  # first question wins when two land in one chapter
    rows = []
    for i, c in enumerate(chapters):
        q = by_idx.get(i)
        if q:
            qt = plain(q["q"]).strip()
            rows.append((c["t"], qt if len(qt) <= CHAPTER_TITLE_MAX else plain(c["title"]), plain(q["a"]).strip()))
        else:
            rows.append((c["t"], plain(c["title"]), None))
    return rows


def render_description(ep: dict, brand: dict, layout: str = "classic") -> str:
    """layout 'classic': question bullets + chapter list. 'merged': one list in which every question is a timestamped
    chapter followed by its one-sentence answer (no separate question list, no repeated question text)."""
    vid = ep["video"]
    hours = (vid.get("duration_seconds") or 0) >= 3600
    out: list[str] = []
    top, footer = _promo_and_footer(brand["description"])
    header = (brand["description"].get("header") or "").strip()
    if header:  # the brand's fixed header – always first, verbatim
        out += [header, DESC_SEP, ""]
    if top:
        out += [top, DESC_SEP, ""]
    out.append(plain(ep["answer_short"]).strip())
    if ep.get("context"):
        out += ["", plain(ep["context"]).strip()]
    if layout == "merged":
        out += ["", f"{brand['description']['article_label']} {article_url(ep, brand)}"]
        out += ["", brand["description"].get("qa_chapters_heading", "⏱️ Въпроси и глави:")]
        for t, line, answer in _qa_chapters(ep):
            out.append(f"{fmt_ts(t, hours)} {line}")
            if answer:
                out.append(answer)
    else:
        out += ["", brand["description"]["questions_heading"]]
        out += [f"• {plain(q['q'])}" for q in ep["questions"]]
        out += ["", f"{brand['description']['article_label']} {article_url(ep, brand)}"]
        out += ["", brand["description"]["chapters_heading"]]
        out += [f"{fmt_ts(c['t'], hours)} {plain(c['title'])}" for c in ep["chapters"]]
    if ep.get("freshness_note"):
        out += ["", f"ℹ️ {plain(ep['freshness_note'])}"]
    people = ep.get("people", [])
    host = [p["name"] for p in people if p.get("role") == "host"]
    guests = [f"{p['name']} ({p.get('job_title', '')})".replace(" ()", "") for p in people if p.get("role") == "guest"]
    who = []
    if host:
        who.append(f"{brand['description'].get('host_label', '🎙️ Водещ:')} {', '.join(host)}")
    if guests:
        who.append(f"{brand['description'].get('guest_label', '👤 Гост:')} {', '.join(guests)}")
    if who:
        out += ["", *who]
    out += ["", footer]
    if ep.get("hashtags"):
        out += ["", " ".join(h if h.startswith("#") else "#" + h for h in ep["hashtags"][:3])]
    return "\n".join(out).strip() + "\n"

# ----------------------------------------------------------------------------
# 2) Gutenberg article
# ----------------------------------------------------------------------------

def _attrs(d: dict) -> str:
    return (" " + json.dumps(d, ensure_ascii=False, separators=(",", ":"))) if d else ""


def b_paragraph(text_html: str, cls: str | None = None) -> str:
    a = {"className": cls} if cls else {}
    c = f' class="{cls}"' if cls else ""
    return f"<!-- wp:paragraph{_attrs(a)} -->\n<p{c}>{text_html}</p>\n<!-- /wp:paragraph -->"


def b_heading(text: str, level: int = 2, anchor: str | None = None) -> str:
    a = {}
    if level != 2:
        a["level"] = level
    if anchor:
        a["anchor"] = anchor
    idattr = f' id="{anchor}"' if anchor else ""
    return (f"<!-- wp:heading{_attrs(a)} -->\n<h{level} class=\"wp-block-heading\"{idattr}>{inline_md(text)}"
            f"</h{level}>\n<!-- /wp:heading -->")


def b_list(items_html: list[str], ordered: bool = False) -> str:
    tag = "ol" if ordered else "ul"
    a = {"ordered": True} if ordered else {}
    lis = "".join(f"<!-- wp:list-item -->\n<li>{i}</li>\n<!-- /wp:list-item -->" for i in items_html)
    return f"<!-- wp:list{_attrs(a)} -->\n<{tag} class=\"wp-block-list\">{lis}</{tag}>\n<!-- /wp:list -->"


def b_table(headers: list[str], rows: list[list[str]], caption: str | None = None) -> str:
    th = "".join(f"<th>{inline_md(h)}</th>" for h in headers)
    trs = "".join("<tr>" + "".join(f"<td>{inline_md(c)}</td>" for c in r) + "</tr>" for r in rows)
    cap = f"<figcaption class=\"wp-element-caption\">{inline_md(caption)}</figcaption>" if caption else ""
    return (f"<!-- wp:table {{\"hasFixedLayout\":false}} -->\n<figure class=\"wp-block-table\"><table>"
            f"<thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>{cap}</figure>\n<!-- /wp:table -->")


def b_quote(text: str, cite: str) -> str:
    return (f"<!-- wp:quote -->\n<blockquote class=\"wp-block-quote\">{b_paragraph(inline_md(text))}"
            f"<cite>{inline_md(cite)}</cite></blockquote>\n<!-- /wp:quote -->")


def b_embed(url: str, caption: str | None = None) -> str:
    a = {"url": url, "type": "video", "providerNameSlug": "youtube", "responsive": True,
         "className": "wp-embed-aspect-16-9 wp-has-aspect-ratio"}
    cap = f"<figcaption class=\"wp-element-caption\">{inline_md(caption)}</figcaption>" if caption else ""
    return (f"<!-- wp:embed{_attrs(a)} -->\n<figure class=\"wp-block-embed is-type-video is-provider-youtube "
            f"wp-block-embed-youtube wp-embed-aspect-16-9 wp-has-aspect-ratio\"><div class=\"wp-block-embed__wrapper\">\n"
            f"{url}\n</div>{cap}</figure>\n<!-- /wp:embed -->")


def b_details(summary: str, inner_blocks: list[str]) -> str:
    return (f"<!-- wp:details -->\n<details class=\"wp-block-details\"><summary>{esc(summary)}</summary>"
            + "".join(inner_blocks) + "</details>\n<!-- /wp:details -->")


def b_html(raw: str) -> str:
    return f"<!-- wp:html -->\n{raw}\n<!-- /wp:html -->"


def transcript_blocks(md_text: str) -> list[str]:
    """transcript.edited.md -> paragraph blocks. Lines starting with '#' are skipped,
    sponsor reads, the opening teaser (repeats the body) and standard welcome/farewell wording, marked with
    <!-- sponsor|teaser|boilerplate --> ... <!-- /... -->, are dropped."""
    md_text = re.sub(r"<!--\s*(sponsor|teaser|boilerplate)\s*-->.*?<!--\s*/\1\s*-->", "", md_text, flags=re.S)
    blocks = []
    for para in re.split(r"\n\s*\n", md_text):
        para = " ".join(l.strip() for l in para.strip().splitlines())
        if not para or para.startswith("#"):
            continue
        blocks.append(b_paragraph(inline_md(para)))
    return blocks


def render_article(ep: dict, brand: dict, transcript_md: str | None = None, schema: dict | None = None) -> str:
    vid = ep["video"]
    vurl = watch_url(vid["id"])
    L = brand["article"]["labels"]
    B: list[str] = []
    # 1. video first
    B.append(b_embed(vurl, ep["article"].get("embed_caption") or vid["title"]))
    # 2. answer block
    B.append(b_paragraph(f"<strong>{esc(L['answer'])}</strong> {inline_md(ep['answer_short'])}", "aeo-answer"))
    # 3. freshness / editorial note
    if ep.get("freshness_note"):
        B.append(b_paragraph(f"<em>{inline_md(ep['freshness_note'])}</em>", "aeo-note"))
    # 3b. optional human lead: why a reader should care (after the answer, so the answer stays first)
    if ep["article"].get("intro"):
        B.append(b_paragraph(inline_md(ep["article"]["intro"]), "aeo-intro"))
    # 4. key takeaways
    if ep.get("key_takeaways"):
        B.append(b_heading(L["takeaways"], anchor="osnovni-izvodi"))
        B.append(b_list([inline_md(x) for x in ep["key_takeaways"]]))
    # 5. chapters with deep links
    B.append(b_heading(L["chapters"], anchor="sadarzhanie"))
    B.append(b_list([f'<a href="{esc(watch_url(vid["id"], c["t"]))}">{fmt_ts(c["t"])}</a> – {inline_md(c["title"])}'
                     for c in ep["chapters"]]))
    # 6. body sections: H2 = question, first paragraph = direct answer
    for s in ep.get("sections", []):
        B.append(b_heading(s["h2"], anchor=s.get("anchor")))
        B.append(b_paragraph(inline_md(s["answer"]), "aeo-section-answer"))
        for p in s.get("paragraphs", []):
            B.append(b_paragraph(inline_md(p)))
        if s.get("bullets"):
            B.append(b_list([inline_md(x) for x in s["bullets"]], ordered=s.get("ordered", False)))
        if s.get("table"):
            t = s["table"]
            B.append(b_table(t["headers"], t["rows"], t.get("caption")))
        for q in s.get("quotes", []):
            cite = q["speaker"] + (f", {fmt_ts(q['t'])}" if q.get("t") is not None else "")
            B.append(b_quote(q["text"], cite))
        if s.get("chapter_t") is not None:
            B.append(b_paragraph(f'▶ <a href="{esc(watch_url(vid["id"], s["chapter_t"]))}">'
                                 f'{esc(L["watch_segment"])} ({fmt_ts(s["chapter_t"])})</a>', "aeo-watch"))
    # 7. FAQ (visible, identical to FAQPage schema)
    if ep.get("faq"):
        B.append(b_heading(L["faq"], anchor="chesto-zadavani-vaprosi"))
        for f in ep["faq"]:
            B.append(b_heading(f["q"], level=3))
            B.append(b_paragraph(inline_md(f["a"])))
    # 8. edited transcript
    if transcript_md:
        B.append(b_heading(L["transcript"], anchor="transkript"))
        B.append(b_details(L["transcript_summary"], transcript_blocks(transcript_md)))
    # 9. authors (E-E-A-T)
    people = ep.get("people", [])
    if people:
        B.append(b_heading(L["authors"], anchor="avtori"))
        for p in people:
            name = f'<a href="{esc(p["url"])}">{esc(p["name"])}</a>' if p.get("url") else esc(p["name"])
            B.append(b_paragraph(f"<strong>{name}</strong>" + (f" – {inline_md(p['bio'])}" if p.get("bio") else ""),
                                 "aeo-author"))
    # 10. related answers
    rel = ep["article"].get("related") or []
    if rel:
        B.append(b_heading(L["related"], anchor="svarzani"))
        B.append(b_list([f'<a href="{esc(r["url"])}">{esc(r["title"])}</a>' for r in rel]))
    # 11. disclaimer
    B.append(b_paragraph(f"<em>{inline_md(brand['article']['disclaimer'])}</em>", "aeo-disclaimer"))
    # 12. JSON-LD (only when no SEO plugin owns the schema)
    if schema is not None and brand["article"].get("jsonld_in_content", True):
        B.append(b_html('<script type="application/ld+json">'
                        + json.dumps(schema, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
                        + "</script>"))
    return "\n\n".join(B) + "\n"

# ----------------------------------------------------------------------------
# 3) schema.org JSON-LD
# ----------------------------------------------------------------------------

def render_schema(ep: dict, brand: dict) -> dict:
    vid, org = ep["video"], brand["organization"]
    url = article_url(ep, brand)
    dur = vid.get("duration_seconds") or 0
    clips = []
    ch = ep["chapters"]
    for i, c in enumerate(ch):
        end = ch[i + 1]["t"] if i + 1 < len(ch) else dur
        clips.append({"@type": "Clip", "name": plain(c["title"]), "startOffset": int(c["t"]),
                      "endOffset": int(end), "url": watch_url(vid["id"], c["t"] or 1)})
    persons = [{"@type": "Person", "name": p["name"], **({"jobTitle": p["job_title"]} if p.get("job_title") else {}),
                **({"url": p["url"]} if p.get("url") else {})} for p in ep.get("people", [])]
    org_node = {"@type": "Organization", "@id": org["url"].rstrip("/") + "/#organization", "name": org["name"] or brand.get("channel", ""),
                "url": org["url"], **({"logo": org["logo"]} if org.get("logo") else {}),
                **({"sameAs": org["same_as"]} if org.get("same_as") else {})}
    video = {
        "@type": "VideoObject", "@id": url + "#video", "name": vid["title"],
        "description": plain(ep["answer_short"]),
        "thumbnailUrl": vid.get("thumbnail_url") or f"https://i.ytimg.com/vi/{vid['id']}/maxresdefault.jpg",
        "uploadDate": vid.get("upload_date"), "duration": iso_duration(dur),
        "embedUrl": f"https://www.youtube.com/embed/{vid['id']}", "contentUrl": watch_url(vid["id"]),
        "inLanguage": brand.get("language", "bg"), "publisher": {"@id": org_node["@id"]},
        "hasPart": clips,
    }
    if ep.get("transcript_text_for_schema"):
        video["transcript"] = ep["transcript_text_for_schema"]
    article = {
        "@type": "Article", "@id": url + "#article", "headline": vid["title"][:110],
        "description": ep["article"].get("meta_description") or plain(ep["answer_short"]),
        "inLanguage": brand.get("language", "bg"), "mainEntityOfPage": url,
        "datePublished": ep["article"].get("date_published") or "{{DATE_PUBLISHED}}",
        "dateModified": ep["article"].get("date_modified") or ep["article"].get("date_published") or "{{DATE_PUBLISHED}}",
        "author": persons or [{"@id": org_node["@id"]}], "publisher": {"@id": org_node["@id"]},
        "image": video["thumbnailUrl"], "video": {"@id": video["@id"]},
        "about": ep["article"].get("tags", [])[:5],
    }
    graph = [article, video]
    if ep.get("faq"):
        graph.append({"@type": "FAQPage", "@id": url + "#faq", "mainEntity": [
            {"@type": "Question", "name": plain(f["q"]),
             "acceptedAnswer": {"@type": "Answer", "text": plain(f["a"])}} for f in ep["faq"]]})
    graph.append(org_node)
    return {"@context": "https://schema.org", "@graph": graph}

# ----------------------------------------------------------------------------
# package = all renders
# ----------------------------------------------------------------------------

def available_outputs(ep: dict) -> list[str]:
    """Outputs whose content exists in episode.json: the YouTube description is the core, the others are added by
    its own command (wp-article writes sections/faq)."""
    out = ["youtube"]
    if ep.get("sections") and ep.get("faq"):
        out.append("wordpress")
    return out


ARTICLE_VARIANT_FILES = {"classic": ("article.wp.html", "wp-post-fields.json", "schema.jsonld"),
                         "v2": ("article.v2.wp.html", "wp-post-fields.v2.json", "schema.v2.jsonld")}


def article_variant(ep: dict, variant: str, ep_dir: Path | None = None) -> dict:
    """A copy of the episode whose `article` carries the overrides of a variant (intro, seo_title, meta_description,
    secondary_keyphrases, excerpt …), read from `work/article.<variant>.json` or `article.<variant>` in episode.json.
    The default article and episode.json are never touched."""
    if variant == "classic":
        return ep
    over = dict(ep["article"].get(variant) or {})
    if ep_dir is not None:
        f = find_work_file(ep_dir, f"article.{variant}.json")
        if f.exists():
            over.update(load_json(f))
    art = {**ep["article"], **over}
    art.pop(variant, None)
    return {**ep, "article": art}


def render_package(ep_dir: Path, brand: dict, outputs: list[str] | None = None, layout: str = "classic",
                   article: str = "classic") -> dict:
    """Render the requested outputs (default: every output whose content exists) into the episode folder.
    Paste-ready files go to the folder itself, schema.jsonld to work/."""
    ep_dir = Path(ep_dir)
    ep = load_episode(ep_dir)
    outputs = list(outputs) if outputs else available_outputs(ep)
    unknown = [o for o in outputs if o not in OUTPUT_FILES]
    if unknown:
        return {"ok": False, "errors": [f"Unknown output {unknown}; use {list(OUTPUT_FILES)}."]}
    written, skipped = [], []
    result: dict = {}
    if "youtube" in outputs:
        if layout not in DESCRIPTION_LAYOUT_FILES:
            return {"ok": False, "errors": [f"Unknown description layout '{layout}'; use {list(DESCRIPTION_LAYOUT_FILES)}."]}
        text = render_description(ep, brand, layout)
        fname = DESCRIPTION_LAYOUT_FILES[layout]
        (ep_dir / fname).write_text(text, encoding="utf-8")
        written.append(fname)
        result["description_chars"] = len(text)
        if len(text) > YT_DESCRIPTION_LIMIT:
            result["warning"] = f"{fname} is {len(text)} chars (limit {YT_DESCRIPTION_LIMIT})."
    if "wordpress" in outputs:
        if not (ep.get("sections") and ep.get("faq")):
            skipped.append("wordpress (episode.json has no sections/faq yet – run /video2aeo:wp-article)")
        else:
            if article not in ARTICLE_VARIANT_FILES:
                return {"ok": False, "errors": [f"Unknown article variant '{article}'; use {list(ARTICLE_VARIANT_FILES)}."]}
            art_file, fields_file, schema_file = ARTICLE_VARIANT_FILES[article]
            ep = article_variant(ep, article, ep_dir)
            tr_path = find_work_file(ep_dir, ep.get("transcript_file") or "transcript.edited.md")
            transcript_md = tr_path.read_text(encoding="utf-8") if tr_path.exists() else None
            schema = render_schema(ep, brand)
            work_file(ep_dir, schema_file).write_text(
                json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (ep_dir / art_file).write_text(render_article(ep, brand, transcript_md, schema), encoding="utf-8")
            meta = {k: ep["article"].get(k) for k in ("seo_title", "slug", "meta_description", "focus_keyphrase",
                                                       "category", "tags")}
            for k in ("secondary_keyphrases", "excerpt"):
                if ep["article"].get(k):
                    meta[k] = ep["article"][k]
            meta["title"] = ep["video"]["title"]
            meta["url"] = article_url(ep, brand)
            (ep_dir / fields_file).write_text(
                json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            written += [art_file, fields_file, f"{WORK_DIR}/{schema_file}"]
            result["transcript_included"] = transcript_md is not None
    return {"written": written, "skipped": skipped, **result}

# ----------------------------------------------------------------------------
# validation
# ----------------------------------------------------------------------------

def validate_chapters(chapters: list[dict], duration: float | None) -> tuple[list[str], list[str]]:
    errs, warns = [], []
    if len(chapters) < 3:
        errs.append(f"YouTube needs at least 3 chapters (have {len(chapters)}).")
    if chapters and chapters[0]["t"] != 0:
        errs.append("First chapter must start at 00:00.")
    for i, c in enumerate(chapters):
        title = c["title"].strip()
        if title.lower().strip(" .:–-") in GENERIC_CHAPTERS:
            errs.append(f"Generic chapter title not allowed: '{title}' at {fmt_ts(c['t'])}.")
        if len(title) > 70:
            warns.append(f"Chapter title over 70 chars will be truncated: '{title[:40]}…'")
        if i and c["t"] <= chapters[i - 1]["t"]:
            errs.append(f"Chapters not ascending at {fmt_ts(c['t'])}.")
        nxt = chapters[i + 1]["t"] if i + 1 < len(chapters) else duration
        if nxt is not None and nxt - c["t"] < 10:
            errs.append(f"Chapter at {fmt_ts(c['t'])} is shorter than 10 s.")
    return errs, warns


def _block_balance(doc: str) -> list[str]:
    errs, stack = [], []
    for m in re.finditer(r"<!-- (/?)wp:([a-z0-9/-]+)(?: \{.*?\})?\s*(/?)-->", doc):
        closing, name, selfclose = m.group(1), m.group(2), m.group(3)
        if selfclose:
            continue
        if not closing:
            stack.append(name)
        elif not stack or stack.pop() != name:
            errs.append(f"Unbalanced block comment near: {m.group(0)}")
            break
    if stack:
        errs.append(f"Unclosed blocks: {stack}")
    return errs


def validate_package(ep_dir: Path, brand: dict, outputs: list[str] | None = None) -> dict:
    """Core checks (answer, questions, chapters) always run; each output is checked only when it is requested or its
    file already exists, so the YouTube command never fails on a missing article."""
    ep_dir = Path(ep_dir)
    errors, warnings, placeholders = [], [], set()
    ep = load_episode(ep_dir)
    present = [o for o in OUTPUT_ORDER if (ep_dir / OUTPUT_FILES[o]).exists()]
    outputs = list(outputs) if outputs else (present or ["youtube"])
    wanted = {"answer_short", "questions", "chapters", "article"}
    if "wordpress" in outputs:
        wanted |= {"faq", "sections"}
    for key in sorted(wanted):
        if not ep.get(key):
            errors.append(f"episode.json is missing '{key}'.")
    if ep.get("article") and not ep["article"].get("slug"):
        errors.append("episode.json article.slug is missing (the description links to the article).")
    if len(re.findall(r"[.!?](\s|$)", ep.get("answer_short", ""))) > 4:
        warnings.append("answer_short is longer than ~3 sentences – keep it a direct answer.")
    if not (5 <= len(ep.get("questions", [])) <= 8):
        warnings.append("Aim for 5–8 questions in the mini-index.")
    if "wordpress" in outputs and not (5 <= len(ep.get("faq", [])) <= 8):
        warnings.append("Aim for 5–8 FAQ entries.")
    if "wordpress" in outputs and ep.get("article"):
        art = ep["article"]
        if len(art.get("seo_title", "")) > 60:
            warnings.append(f"seo_title is {len(art['seo_title'])} chars (aim for ≤ 60).")
        if not art.get("meta_description"):
            warnings.append("article.meta_description is missing.")
        elif len(art["meta_description"]) > 155:
            warnings.append(f"meta_description is {len(art['meta_description'])} chars (aim for ≤ 155).")
        if not (3 <= len(art.get("tags", [])) <= 6):
            warnings.append("Aim for 3–6 tags.")
        if len(art.get("secondary_keyphrases", [])) > 4:
            warnings.append("Use at most 4 secondary_keyphrases.")
        kp = (art.get("focus_keyphrase") or "").lower()
        if not kp:
            warnings.append("article.focus_keyphrase is missing.")
        elif kp not in (ep["video"].get("title", "") + " " + plain(ep.get("answer_short", ""))).lower():
            warnings.append("focus_keyphrase appears neither in the title nor in the first paragraph.")
    e, w = validate_chapters(ep.get("chapters", []), ep["video"].get("duration_seconds"))
    errors += e
    warnings += w
    # description
    if "youtube" in outputs:
        d_path = ep_dir / OUTPUT_FILES["youtube"]
        if d_path.exists():
            d = d_path.read_text(encoding="utf-8")
            placeholders |= set(PLACEHOLDER_RE.findall(d))
            if "<" in d or ">" in d:
                errors.append("YouTube description contains '<' or '>' – YouTube rejects these.")
            if len(d) > YT_DESCRIPTION_LIMIT:
                errors.append(f"Description is {len(d)} chars (limit {YT_DESCRIPTION_LIMIT}).")
            elif len(d) > YT_DESCRIPTION_LIMIT - YT_DESCRIPTION_MARGIN:
                warnings.append(f"Description is {len(d)} chars – under {YT_DESCRIPTION_MARGIN} chars of margin.")
            body = d.strip()
            top, _ = _promo_and_footer(brand["description"])
            header = (brand["description"].get("header") or "").strip()
            if header and body.startswith(header):
                if len(header) > 300 or header.count("\n") > 3:
                    warnings.append("The description header is long – the direct answer should start within ~3 lines.")
                body = body[len(header):].lstrip().removeprefix(DESC_SEP).strip()
            if top and body.startswith(top):
                if len(top) > 300 or top.count("\n") > 3:
                    warnings.append("The promo block at the top is long – the direct answer should start within ~3 lines.")
                body = body[len(top):].lstrip().removeprefix(DESC_SEP).strip()
            if brand["description"].get("promo_position", "end") not in PROMO_POSITIONS:
                warnings.append(f"description.promo_position must be one of {PROMO_POSITIONS} – rendered at the end.")
            first = body.split("\n", 1)[0]
            if len(first) < 80:
                warnings.append("Description should open with a 2–3 sentence direct answer.")
        else:
            errors.append("youtube-description.txt not rendered yet.")
    # article
    if "wordpress" in outputs:
        a_path = ep_dir / OUTPUT_FILES["wordpress"]
        if a_path.exists():
            a = a_path.read_text(encoding="utf-8")
            placeholders |= set(PLACEHOLDER_RE.findall(a))
            errors += _block_balance(a)
            first_block = re.search(r"<!-- wp:([a-z/-]+)", a)
            if not first_block or first_block.group(1) != "embed":
                errors.append("The first article block must be the YouTube embed.")
            if "aeo-answer" not in a:
                errors.append("Article is missing the answer block.")
            if re.search(r"<h[23][^>]*>\s*</h[23]>", a):
                errors.append("Empty heading in article.")
        else:
            errors.append("article.wp.html not rendered yet.")
        s_path = find_work_file(ep_dir, "schema.jsonld")
        if s_path.exists():
            try:
                schema = json.loads(s_path.read_text(encoding="utf-8"))
                placeholders |= set(PLACEHOLDER_RE.findall(json.dumps(schema, ensure_ascii=False)))
                faq_nodes = [n for n in schema["@graph"] if n.get("@type") == "FAQPage"]
                if faq_nodes:
                    names = [q["name"] for q in faq_nodes[0]["mainEntity"]]
                    if names != [plain(f["q"]) for f in ep.get("faq", [])]:
                        errors.append("FAQ schema differs from the visible FAQ.")
                vids = [n for n in schema["@graph"] if n.get("@type") == "VideoObject"]
                if not vids or not vids[0].get("uploadDate"):
                    errors.append("VideoObject needs uploadDate.")
            except json.JSONDecodeError as ex:
                errors.append(f"schema.jsonld is not valid JSON: {ex}")
    # numbers must be traceable to the transcript or claims
    corpus = ""
    for f in ("transcript.raw.txt", "transcript.edited.md"):
        path = find_work_file(ep_dir, f)
        if path.exists():
            corpus += path.read_text(encoding="utf-8")
    corpus += " ".join(c.get("text", "") + " " + c.get("note", "") for c in ep.get("claims", []))
    corpus_n = corpus.replace(" ", "").replace(",", ".")
    copy = " ".join([ep.get("answer_short", ""), *ep.get("key_takeaways", []),
                     *(f["a"] for f in ep.get("faq", [])), *(s.get("answer", "") for s in ep.get("sections", []))])
    if corpus:
        for num in sorted(set(re.findall(r"\d+(?:[.,]\d+)?", copy))):
            n = num.replace(",", ".")
            if len(n) >= 2 and n not in corpus_n and n not in ("2024", "2025", "2026", "2027"):
                warnings.append(f"Number '{num}' in the copy is not found in transcript or claims – check it.")
    # claims needing attention
    open_claims = [c for c in ep.get("claims", []) if c.get("status", "unverified") == "unverified"
                   and c.get("type") in ("fact", "forecast")]
    if open_claims:
        warnings.append(f"{len(open_claims)} fact/forecast claims are still 'unverified' (Gate A).")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "placeholders": sorted(placeholders),
            "outputs_checked": outputs}


def write_review(ep_dir: Path, brand: dict, result: dict) -> Path:
    """Write the review sheet to work/review.md."""
    path = work_file(ep_dir, "review.md")
    path.write_text(review_sheet(ep_dir, brand, result), encoding="utf-8")
    return path


def review_sheet(ep_dir: Path, brand: dict, result: dict) -> str:
    ep = load_episode(ep_dir)
    checked = ", ".join(result.get("outputs_checked", [])) or "youtube"
    lines = [f"# Review – {ep['video']['title']}", "",
             f"**Status:** {'✅ ready for approval' if result['ok'] else '❌ fix errors first'} (checked: {checked})", ""]
    if result["errors"]:
        lines += ["## Errors (block publishing)", *[f"- {e}" for e in result["errors"]], ""]
    if result["warnings"]:
        lines += ["## Warnings", *[f"- {w}" for w in result["warnings"]], ""]
    if result["placeholders"]:
        lines += ["## Placeholders to fill", *[f"- `{p}`" for p in result["placeholders"]], ""]
    art = ep.get("article") or {}
    if "wordpress" in result.get("outputs_checked", []):
        lines += ["## WordPress fields", f"- Title (= video title): {ep['video']['title']}",
                  f"- SEO title: {art.get('seo_title', '')}", f"- Slug: {art.get('slug', '')}",
                  f"- Meta description: {art.get('meta_description', '')}",
                  f"- Focus keyphrase: {art.get('focus_keyphrase', '')}",
                  f"- Category: {art.get('category', '')}", f"- Tags: {', '.join(art.get('tags', []))}", ""]
    lines += ["## Fact-check", "| t | speaker | type | status | claim | note |", "|---|---|---|---|---|---|"]
    for c in ep.get("claims", []):
        t = fmt_ts(c["t"]) if c.get("t") is not None else ""
        lines.append(f"| {t} | {c.get('speaker', '')} | {c.get('type', '')} | {c.get('status', 'unverified')} | "
                     f"{c.get('text', '').replace('|', '/')} | {c.get('note', '').replace('|', '/')} |")
    g = ep.get("gates", {})
    lines += ["", "## Gates",
              f"- [{'x' if g.get('A') else ' '}] Gate A – transcript, names, numbers, chapters, title {g.get('A') or ''}",
              f"- [{'x' if g.get('youtube') or g.get('B') else ' '}] YouTube description approved "
              f"{g.get('youtube') or g.get('B') or ''}",
              f"- [{'x' if g.get('wordpress') else ' '}] WordPress article approved {g.get('wordpress') or ''}", ""]
    return "\n".join(lines)
