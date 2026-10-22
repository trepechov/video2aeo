"""
video2aeo pipeline state for long episodes (stdlib only, Python 3.9).

A long transcript is edited in chunks that each land in a file, so a crash loses at most one chunk, and the state of
the whole pipeline is derived from the files on disk (`episode_status`) instead of being remembered by the model.

    work/chunks/index.json        chunk list + hash of the raw transcript they were cut from
    work/chunks/NN.raw.txt        raw paragraphs of chunk NN          (written by split_transcript)
    work/chunks/NN.context.txt    last paragraphs of the previous chunk, read-only context for the editor
    work/chunks/NN.edited.md      the editor's output for chunk NN    (written by the transcript-editor agent)
    work/map/NN.json              knowledge-map notes for chunk NN    (written by the knowledge-mapper, long episodes)
    work/progress.json            attempts, last error and deferred gates; never the source of truth for "done"
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
from pathlib import Path

import aeo_lib as L

CHUNKS_DIR = "chunks"
MAP_DIR = "map"
PROGRESS_FILE = "progress.json"
DEFAULT_CHUNK_MINUTES = 10
SINGLE_CALL_UNDER_MINUTES = 25  # shorter episodes are edited in one call
MIN_CHUNK_MINUTES = 3
MARKERS = ("sponsor", "teaser", "boilerplate")
GATES = {"gate_A": "A", "gate_youtube": "youtube"}
STEPS = ("transcript", "edit_transcript", "knowledge_map", "gate_A", "description", "validate", "gate_youtube")

_STAMP = r"\d{1,2}:\d{2}(?::\d{2})?"
_RAW_PARA = re.compile(r"^\[(%s)\]\s*(.*)$" % _STAMP, re.S)
_EDITED_STAMP = re.compile(r"\*\*\[(%s)\]" % _STAMP)
_COMMENT = re.compile(r"<!--.*?-->", re.S)


def _now() -> str:
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _words(text: str) -> int:
    return len(_EDITED_STAMP.sub("", _COMMENT.sub("", text)).split())


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    L._write_atomic(path, json.dumps(data, ensure_ascii=False, indent=1) + "\n")


def _read_json(path: Path, default=None):
    try:
        return L.load_json(path)
    except (OSError, ValueError):
        return default


def _paragraphs(raw: str) -> list:
    """[(start_seconds, text)] from the raw reading copy ('[MM:SS] text' paragraphs); unstamped text joins the previous one."""
    out = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        block = block.strip()
        if not block:
            continue
        m = _RAW_PARA.match(block)
        if m:
            out.append([L.parse_ts(m.group(1)), block])
        elif out:
            out[-1][1] += "\n" + block
    return [(s, t) for s, t in out]


# ----------------------------------------------------------------------------
# progress.json
# ----------------------------------------------------------------------------

def load_progress(ep_dir) -> dict:
    data = _read_json(L.work_dir(Path(ep_dir)) / PROGRESS_FILE, {})
    data = data if isinstance(data, dict) else {}
    data.setdefault("steps", {})
    data.setdefault("deferred_gates", [])
    return data


def record_progress(ep_dir, step: str, error: str | None = None, ok: bool | None = None,
                    defer_gate: str | None = None, undefer_gate: str | None = None) -> dict:
    """Note an attempt (error given), a success (ok=True) or a deferred gate (unattended run). Returns the entry."""
    ep_dir = Path(ep_dir)
    prog = load_progress(ep_dir)
    entry = prog["steps"].setdefault(step, {"attempts": 0, "last_error": ""})
    if error:
        entry["attempts"] += 1
        entry["last_error"] = str(error)[:500]
    elif ok:
        entry["last_error"] = ""
    entry["updated"] = _now()
    if defer_gate and defer_gate not in prog["deferred_gates"]:
        prog["deferred_gates"].append(defer_gate)
    if undefer_gate in prog["deferred_gates"]:
        prog["deferred_gates"].remove(undefer_gate)
    _write_json(L.work_file(ep_dir, PROGRESS_FILE), prog)
    return {"ok": True, "step": step, **entry, "deferred_gates": prog["deferred_gates"]}


# ----------------------------------------------------------------------------
# chunks
# ----------------------------------------------------------------------------

def _chunks_dir(ep_dir: Path) -> Path:
    return L.work_dir(ep_dir) / CHUNKS_DIR


def _load_index(ep_dir: Path):
    idx = _read_json(_chunks_dir(ep_dir) / "index.json")
    return idx if isinstance(idx, dict) and isinstance(idx.get("chunks"), list) else None


def _check_edited(chunk: dict, text: str, raw_text: str) -> tuple:
    """(errors, warnings) for one edited chunk. Errors mean: redo this chunk."""
    errors, warnings = [], []
    stamps = [L.parse_ts(m) for m in _EDITED_STAMP.findall(text)]
    if not stamps:
        return ["no paragraph starts with a **[MM:SS] Speaker:** stamp"], warnings
    lo, hi = chunk["start"] - 60, (chunk["range_end"] if chunk["range_end"] is not None else float("inf")) + 60
    outside = [L.fmt_ts(s) for s in stamps if not lo <= s <= hi]
    if outside:
        errors.append(f"stamps outside this chunk ({L.fmt_ts(chunk['start'])}–{L.fmt_ts(chunk['last'])}): {outside[:3]}")
    raw_stamps = {s for s, _ in _paragraphs(raw_text)}
    invented = [L.fmt_ts(s) for s in stamps if s not in raw_stamps]
    if invented:
        warnings.append(f"{len(invented)} stamp(s) are not in the raw chunk (never invent stamps): {invented[:3]}")
    raw_words, ed_words = max(chunk["words"], 1), _words(text)
    ratio = ed_words / raw_words
    if ratio < 0.35:
        errors.append(f"only {ed_words} words for {raw_words} raw words – truncated or summarised")
    elif ratio < 0.6:
        warnings.append(f"{ed_words} words for {raw_words} raw words – check that nothing was summarised")
    if chunk["last"] - max(stamps) > 180:
        errors.append(f"ends at {L.fmt_ts(max(stamps))} but the raw chunk runs to {L.fmt_ts(chunk['last'])} – truncated?")
    for name in MARKERS:
        opened, closed = len(re.findall(r"<!--\s*%s\s*-->" % name, text)), len(re.findall(r"<!--\s*/%s\s*-->" % name, text))
        if opened != closed:
            errors.append(f"unbalanced <!-- {name} --> markers ({opened} open, {closed} closed); close a marker that runs "
                          "past the chunk border and open it again in the next chunk")
    return errors, warnings


def _chunk_state(ep_dir: Path, chunk: dict) -> dict:
    cd = _chunks_dir(ep_dir)
    edited = cd / f"{chunk['n']:02d}.edited.md"
    if not edited.exists():
        return {"n": chunk["n"], "state": "todo"}
    try:
        text = edited.read_text(encoding="utf-8")
        raw_text = (cd / f"{chunk['n']:02d}.raw.txt").read_text(encoding="utf-8")
    except OSError as ex:
        return {"n": chunk["n"], "state": "invalid", "errors": [str(ex)]}
    errors, warnings = _check_edited(chunk, text, raw_text)
    return {"n": chunk["n"], "state": "invalid" if errors else "done", "errors": errors, "warnings": warnings}


def split_transcript(ep_dir, minutes=None, force: bool = False) -> dict:
    """Cut work/transcript.raw.txt into chunks at paragraph stamps. Safe to call again: the same transcript and settings
    return the existing split; a changed transcript or `minutes` re-splits but keeps every edited chunk whose raw text
    is unchanged. `minutes` omitted: one chunk for episodes shorter than SINGLE_CALL_UNDER_MINUTES, else 10-minute chunks."""
    ep_dir = Path(ep_dir)
    raw_path = L.find_work_file(ep_dir, "transcript.raw.txt")
    if not raw_path.exists():
        return {"ok": False, "error": "work/transcript.raw.txt is missing – import or fetch the transcript first."}
    raw = raw_path.read_text(encoding="utf-8")
    paras = _paragraphs(raw)
    if not paras:
        return {"ok": False, "error": "work/transcript.raw.txt has no '[MM:SS] text' paragraphs."}
    try:
        requested = None if minutes in (None, "", 0) else max(MIN_CHUNK_MINUTES, float(minutes))
    except (TypeError, ValueError):
        return {"ok": False, "error": f"minutes must be a number, got {minutes!r}."}
    sha = _sha(raw)
    old = _load_index(ep_dir)
    if old and not force and old.get("raw_sha") == sha and old.get("requested") == requested:
        return {"ok": True, "reused": True, **_summary(ep_dir, old)}

    duration = paras[-1][0]
    size = requested if requested else (DEFAULT_CHUNK_MINUTES if duration >= SINGLE_CALL_UNDER_MINUTES * 60 else None)
    groups, cur = [], []
    for start, text in paras:
        if cur and size and start >= cur[0][0] + size * 60:
            groups.append(cur)
            cur = []
        cur.append((start, text))
    groups.append(cur)

    kept = {}  # raw hash -> edited text of the old split, so a re-split never throws finished work away
    if old:
        for c in old["chunks"]:
            f = _chunks_dir(ep_dir) / f"{c['n']:02d}.edited.md"
            if f.exists() and _chunk_state(ep_dir, c)["state"] == "done":
                kept[c["raw_sha"]] = f.read_text(encoding="utf-8")
    cd = _chunks_dir(ep_dir)
    cd.mkdir(parents=True, exist_ok=True)
    for f in cd.iterdir():
        f.unlink()
    chunks = []
    for i, g in enumerate(groups, 1):
        raw_text = "\n\n".join(t for _, t in g) + "\n"
        chunks.append({
            "n": i, "start": g[0][0], "last": g[-1][0], "start_ts": L.fmt_ts(g[0][0]), "last_ts": L.fmt_ts(g[-1][0]),
            "range_end": groups[i][0][0] if i < len(groups) else None, "paragraphs": len(g), "words": len(raw_text.split()),
            "raw_sha": _sha(raw_text)})
        L._write_atomic(cd / f"{i:02d}.raw.txt", raw_text)
        if i > 1:
            L._write_atomic(cd / f"{i:02d}.context.txt", "\n\n".join(t for _, t in groups[i - 2][-2:]) + "\n")
        if chunks[-1]["raw_sha"] in kept:
            L._write_atomic(cd / f"{i:02d}.edited.md", kept[chunks[-1]["raw_sha"]])
    index = {"raw_sha": sha, "requested": requested, "minutes": size or 0, "created": _now(), "chunks": chunks}
    _write_json(cd / "index.json", index)
    return {"ok": True, "reused": False, "kept_edited": sorted(n for n in (c["n"] for c in chunks)
                                                               if (cd / f"{n:02d}.edited.md").exists()),
            **_summary(ep_dir, index)}


def _summary(ep_dir: Path, index: dict) -> dict:
    states = [_chunk_state(ep_dir, c) for c in index["chunks"]]
    return {"total": len(states), "minutes": index.get("minutes", 0),
            "done": [s["n"] for s in states if s["state"] == "done"],
            "todo": [s["n"] for s in states if s["state"] == "todo"],
            "invalid": [{"n": s["n"], "errors": s["errors"]} for s in states if s["state"] == "invalid"],
            "dir": f"{L.WORK_DIR}/{CHUNKS_DIR}",
            "chunks": [{"n": c["n"], "range": f"{c['start_ts']}–{c['last_ts']}", "raw": f"{CHUNKS_DIR}/{c['n']:02d}.raw.txt",
                        "context": f"{CHUNKS_DIR}/{c['n']:02d}.context.txt" if c["n"] > 1 else "",
                        "edited": f"{CHUNKS_DIR}/{c['n']:02d}.edited.md"} for c in index["chunks"]]}


def merge_transcript(ep_dir) -> dict:
    """Join the edited chunks into work/transcript.edited.md after checking every one of them."""
    ep_dir = Path(ep_dir)
    index = _load_index(ep_dir)
    if not index:
        return {"ok": False, "error": "No chunks – run split_transcript first."}
    raw_path = L.find_work_file(ep_dir, "transcript.raw.txt")
    if raw_path.exists() and _sha(raw_path.read_text(encoding="utf-8")) != index["raw_sha"]:
        return {"ok": False, "error": "The raw transcript changed after it was split – run split_transcript again "
                                      "(finished chunks with unchanged text are kept)."}
    cd = _chunks_dir(ep_dir)
    states = [_chunk_state(ep_dir, c) for c in index["chunks"]]
    bad = [s for s in states if s["state"] != "done"]
    if bad:
        return {"ok": False, "error": "Not every chunk is edited and valid.",
                "todo": [s["n"] for s in bad if s["state"] == "todo"],
                "invalid": [{"n": s["n"], "errors": s["errors"]} for s in bad if s["state"] == "invalid"]}
    parts, warnings = [], []
    for s, c in zip(states, index["chunks"]):
        text = (cd / f"{c['n']:02d}.edited.md").read_text(encoding="utf-8").strip()
        if c["n"] > 1:  # only the first chunk carries the title and speakers line
            lines = text.splitlines()
            while lines and (lines[0].startswith("# ") or not lines[0].strip()):
                lines.pop(0)
            if lines and not lines[0].startswith(("**[", "<!--")) and lines[0].strip() and not _EDITED_STAMP.search(lines[0]):
                lines.pop(0)  # the speakers line that follows the title
            text = "\n".join(lines).strip()
        parts.append(text)
        warnings += [f"chunk {c['n']}: {w}" for w in s.get("warnings", [])]
    merged = "\n\n".join(parts) + "\n"
    for name in MARKERS:  # a block that runs over a chunk border was closed and reopened: make it one block again
        merged = re.sub(r"<!--\s*/%s\s*-->\s*<!--\s*%s\s*-->\n?" % (name, name), "", merged)
    if not merged.lstrip().startswith("# "):
        warnings.append("the file does not start with '# Транскрипт – <title>' (the first chunk should carry it)")
    outside_teaser = re.sub(r"<!--\s*teaser\s*-->.*?<!--\s*/teaser\s*-->", "", merged, flags=re.S)
    stamps = [L.parse_ts(m) for m in _EDITED_STAMP.findall(outside_teaser)]
    back = [L.fmt_ts(b) for a, b in zip(stamps, stamps[1:]) if b < a]
    if back:
        warnings.append(f"{len(back)} stamp(s) go backwards outside the teaser, e.g. at {back[:3]}")
    L._write_atomic(L.work_file(ep_dir, "transcript.edited.md"), merged)
    index["merged"] = {"raw_sha": index["raw_sha"], "at": _now()}
    _write_json(cd / "index.json", index)
    record_progress(ep_dir, "edit_transcript", ok=True)
    return {"ok": True, "file": f"{L.WORK_DIR}/transcript.edited.md", "chunks": len(parts), "words": _words(merged),
            "warnings": warnings}


# ----------------------------------------------------------------------------
# episode_status
# ----------------------------------------------------------------------------

def _ranges(nums: list) -> str:
    out, i = [], 0
    nums = sorted(nums)
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else f"{nums[i]}-{nums[j]}")
        i = j + 1
    return ", ".join(out)


def _edit_step(ep_dir: Path, raw_exists: bool) -> dict:
    """State of the transcript-editing step, with the chunk detail."""
    edited = L.find_work_file(ep_dir, "transcript.edited.md")
    index = _load_index(ep_dir)
    raw_path = L.find_work_file(ep_dir, "transcript.raw.txt")
    if not index:
        if edited.exists():  # whole-file edit (older episodes or short ones done in one call)
            return {"done": True, "detail": "transcript.edited.md exists", "chunks": None}
        return {"done": False, "detail": "not split yet", "chunks": None,
                "next": "split_transcript, then edit each chunk" if raw_exists else ""}
    stale = raw_exists and _sha(raw_path.read_text(encoding="utf-8")) != index["raw_sha"]
    if stale:
        return {"done": False, "stale": True, "chunks": None,
                "detail": "the raw transcript changed after it was split",
                "next": "split_transcript again (edited chunks with unchanged text are kept), then edit the rest"}
    summ = _summary(ep_dir, index)
    info = {"total": summ["total"], "done": len(summ["done"]), "todo": summ["todo"], "invalid": summ["invalid"]}
    redo = sorted(summ["todo"] + [i["n"] for i in summ["invalid"]])
    if redo:
        return {"done": False, "chunks": info, "detail": f"{info['done']}/{info['total']} chunks edited",
                "next": f"edit chunk(s) {_ranges(redo)}"}
    merged = index.get("merged")
    if edited.exists() and merged and merged.get("raw_sha") == index["raw_sha"]:
        return {"done": True, "chunks": info, "detail": "merged"}
    return {"done": False, "chunks": info, "detail": "all chunks edited", "next": "merge_transcript"}


def episode_status(ep_dir) -> dict:
    """Where does this episode stand and what is the next action? Derived from the files, so it is right after a crash."""
    ep_dir = Path(ep_dir)
    wd = L.work_dir(ep_dir)
    if not ep_dir.is_dir():
        return {"ok": False, "error": f"{ep_dir} is not a folder."}
    prog = load_progress(ep_dir)
    raw_path = L.find_work_file(ep_dir, "transcript.raw.txt")
    raw_exists = raw_path.exists() and raw_path.stat().st_size > 0
    ep, ep_problem = {}, ""
    ep_file = L.find_work_file(ep_dir, "episode.json")
    if ep_file.exists():
        try:
            ep = L.load_json(ep_file)
        except (OSError, ValueError) as ex:
            ep_problem = f"episode.json is unreadable: {ex}"
    gates = ep.get("gates") or {}
    deferred = prog["deferred_gates"]

    edit = _edit_step(ep_dir, raw_exists)
    index = _load_index(ep_dir)
    map_info = None
    if index and len(index["chunks"]) > 1:
        notes = [c["n"] for c in index["chunks"] if _read_json(wd / MAP_DIR / f"{c['n']:02d}.json") is not None]
        map_info = {"total": len(index["chunks"]), "done": len(notes),
                    "todo": [c["n"] for c in index["chunks"] if c["n"] not in notes]}
    mapped = bool(ep.get("questions")) and bool(ep.get("chapters"))
    if mapped or map_info is None:
        map_next = "knowledge-mapper agent -> work/episode.json"
    elif map_info["todo"]:
        map_next = f"knowledge-mapper in section mode for section(s) {_ranges(map_info['todo'])}"
    else:
        map_next = "knowledge-mapper merge: work/map/*.json -> work/episode.json"
    copy_ready = all(ep.get(k) for k in ("answer_short", "context", "hashtags"))
    rendered = (ep_dir / L.OUTPUT_FILES["youtube"]).exists() and (wd / "review.md").exists()

    steps = [
        {"id": "transcript", "done": raw_exists or L.find_work_file(ep_dir, "transcript.edited.md").exists(),
         "detail": "work/transcript.raw.txt",
         "next": "import_transcript(file) or fetch_transcript(url)"},
        {"id": "edit_transcript", **edit},
        {"id": "knowledge_map", "done": mapped, "detail": ep_problem or ("episode.json has questions and chapters" if mapped else ""),
         "next": map_next, **({"sections": map_info} if map_info and not mapped else {})},
        {"id": "gate_A", "done": bool(gates.get("A")) or "A" in deferred,
         "detail": "deferred (unattended run) – still open" if "A" in deferred and not gates.get("A") else gates.get("A", ""),
         "next": "present Gate A (facts, chapters, title) to the user"},
        {"id": "description", "done": copy_ready, "detail": "answer_short, context, hashtags",
         "next": "complete the description copy in episode.json (Step 4)"},
        {"id": "validate", "done": rendered, "detail": "youtube-description.txt and work/review.md",
         "next": "render_package + validate_package with outputs=[\"youtube\"]"},
        {"id": "gate_youtube", "done": bool(gates.get("youtube")), "detail": gates.get("youtube", ""),
         "next": "send the description to the user for approval"},
    ]
    # a later step cannot be done while an earlier one is not (e.g. a stale raw transcript)
    current = next((s for s in steps if not s["done"]), None)
    done_ids = [s["id"] for s in steps if s["done"] and (current is None or STEPS.index(s["id"]) < STEPS.index(current["id"]))]
    step = current["id"] if current else "done"
    article = "approved" if gates.get("wordpress") else "rendered" if (ep_dir / L.OUTPUT_FILES["wordpress"]).exists() \
        else "content_ready" if ep.get("sections") else "not_started"
    open_gates = [g for g in deferred if not gates.get(g)]
    attempts = (prog["steps"].get(step) or {}).get("attempts", 0)
    out = {
        "ok": True, "episode_dir": str(ep_dir), "step": step, "done": done_ids,
        "pending_gate": GATES.get(step), "open_gates": open_gates,
        "next_action": (current.get("next") or current.get("detail") or "") if current else
                       "Nothing left to do for the YouTube description. Optional next: /video2aeo:wp-article.",
        "detail": current.get("detail", "") if current else "",
        "stale": bool(current and current.get("stale")),
        "chunks": edit.get("chunks"), "sections": map_info, "article": article,
        "attempts": attempts, "last_error": (prog["steps"].get(step) or {}).get("last_error", ""),
        "steps": [{"id": s["id"], "done": s["id"] in done_ids, "detail": s.get("detail", "")} for s in steps],
    }
    return out


def find_unfinished(limit: int = 50):
    """The most recently touched episode under the episodes root that is not done, as its episode_status; None if none."""
    root = L.episodes_root()
    if not root or not root.is_dir():
        return None
    found = []
    for work in root.glob("*/*/" + L.WORK_DIR):
        if not work.is_dir():
            continue
        mt = max([work.stat().st_mtime] + [p.stat().st_mtime for p in work.iterdir()])
        found.append((mt, work.parent))
    for _, d in sorted(found, reverse=True)[:limit]:
        st = episode_status(d)
        if st.get("ok") and st["step"] != "done":
            return st
    return None
