#!/usr/bin/env python3
"""
video2aeo – a tiny local MCP server (stdio, JSON-RPC, stdlib only).

Exposes the deterministic and network steps of the pipeline as tools so the agent
can call them from a Cowork task on the marketer's computer. All writing is done
by Claude; these tools only fetch, assemble and check.
"""
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import aeo_lib as L  # noqa: E402
import aeo_net as N  # noqa: E402
import aeo_pipeline as P  # noqa: E402

SERVER = {"name": "video2aeo", "version": L.load_json(ROOT / ".claude-plugin" / "plugin.json")["version"]}

OUTPUTS = {"type": "array", "items": {"type": "string", "enum": ["youtube", "wordpress"]},
           "description": "Which outputs to handle. Omit for every output that already has content in episode.json. "
                          "/video2aeo:episode passes [\"youtube\"], /video2aeo:wp-article [\"wordpress\"]."}
DIR = {"type": "string", "description": "Absolute path of the episode folder as returned by episode_path: <episodes root>/<series folder>/<yyyy-mm>-<series>-<nn>-<slug>"}
TOOLS = [
    {"name": "setup_status",
     "description": "Preflight check: has the one-time brand setup been done on this computer? Returns configured, missing "
                    "placeholders, unreadable files, warnings, legacy_footer and the current saved values (to pre-fill setup). "
                    "Call it first in every video2aeo workflow; if configured is false run the setup skill.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "check_environment",
     "description": "Check this computer (read-only): Python version and path used by the plugin, whether ~/.video2aeo/ can be "
                    "written, and whether the optional subtitle downloaders are installed. Used by the setup skill.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "save_setup",
     "description": "Write the user-approved setup answers to ~/.video2aeo/ (brand.json, glossary.json, guidelines.md, setup.json). "
                    "brand/glossary are merged over existing files; omitted arguments keep what is saved; skipped optional fields "
                    "are saved empty; the previous guidelines.md is kept as guidelines.md.bak. Only call after the user approved "
                    "the summary. Returns ok/errors plus the new status.",
     "inputSchema": {"type": "object", "properties": {
         "brand": {"type": "object", "description": "Nested subset of config/brand.json, e.g. {\"channel\": \"…\", \"description\": "
                                                    "{\"promo\": \"…\", \"promo_position\": \"end\", \"schedule\": \"…\"}}"},
         "glossary": {"type": "object"},
         "guidelines_md": {"type": "string", "description": "Full text of guidelines.md: existing house rules plus the 'Switched-off guidelines' section"},
         "guidelines_off": {"type": "array", "items": {"type": "string"},
                            "description": "Ids of adjustable guidelines the user switched off (see the guideline catalog)"},
         "models": {"type": "object", "description": "Optional model choice for delegated work, only when the user asks to change it: {\"profile\": \"fast\"|\"balanced\"|\"quality\", \"overrides\": {\"<operation>\": \"haiku\"|\"sonnet\"|\"opus\"|\"fable\"|\"inherit\"}}. Replaces the saved choice; {} goes back to the plugin defaults. Operations and current values: setup_status.models."},
         "episodes_root": {"type": "string", "description": "Absolute path of the one folder that holds all episodes (<root>/<series folder>/<episode>); saved in config.json. Format profiles carry their series folder as brand.formats.<id>.folder (short Latin slug)."}}}},
    {"name": "workspace_status",
     "description": "Is the folder this session runs in a good place for episode files? Call right after setup_status in /video2aeo:episode and "
                    "/video2aeo:wp-article, passing the session folder (run `pwd`). Returns ok, status (ok | inside_episode | suspicious | unknown | "
                    "no_root), the saved episodes_root, episode_dir when the session is inside an episode, reason and next_step. "
                    "When ok is false STOP before reading the transcript and tell the user what next_step says.",
     "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string", "description": "The session's working folder (output of `pwd`); defaults to the server's own folder"}}}},
    {"name": "episode_path",
     "description": "Build and create the episode folder (with work/) inside the episodes root: <root>/<series folder>/<yyyy-mm>-<series>-<nn>-<slug>. "
                    "Always use its result as episode_dir – never invent the path. Without `number` an existing folder with the same slug is "
                    "reused, otherwise the next free number of the series is taken.",
     "inputSchema": {"type": "object", "properties": {
         "slug": {"type": "string", "description": "Short title slug (Latin or Bulgarian; transliterated)"},
         "format": {"type": "string", "description": "Id of the format profile (setup_status.current.formats); omit for the base format (folder _other)"},
         "upload_date": {"type": "string", "description": "Video upload date (YYYYMMDD or YYYY-MM-DD); defaults to today"},
         "number": {"type": "integer", "description": "Episode number in the series; omit to take the next free one"}},
         "required": ["slug"]}},
    {"name": "get_video_info",
     "description": "Get title, channel, thumbnail, upload date, duration and the current description of a YouTube video, plus the "
                    "`coverage` plan (full / balanced / selective) for the knowledge map derived from the duration and the episode's format profile.",
     "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "format": {"type": "string", "description": "Id of the brand's format profile (setup_status.current.formats) of this episode; omit for the base format"}}, "required": ["url"]}},
    {"name": "fetch_transcript",
     "description": "Download the video's subtitles (in the brand language by default) from YouTube to work/transcript.raw.json/.txt in the episode folder. "
                    "Runs on this computer. On failure returns the manual fallback.",
     "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "episode_dir": DIR,
                                                       "lang": {"type": "string", "description": "Subtitle language code; defaults to the brand language"}},
                     "required": ["url", "episode_dir"]}},
    {"name": "import_transcript",
     "description": "Parse a transcript file the user downloaded or pasted (VTT, SRT, YouTube 'MM:SS text' copy, JSON) into work/transcript.raw.*",
     "inputSchema": {"type": "object", "properties": {"file": {"type": "string"}, "episode_dir": DIR, "format": {"type": "string", "description": "Id of the brand's format profile (setup_status.current.formats) of this episode; omit for the base format"}},
                     "required": ["file", "episode_dir"]}},
    {"name": "split_transcript",
     "description": "Cut work/transcript.raw.txt into chunks (work/chunks/NN.raw.txt, with NN.context.txt) so a long transcript is edited piece by piece and a crash loses at most one chunk. "
                    "Episodes under 25 minutes stay one chunk. Safe to call again: the same transcript returns the existing split; a changed transcript or `minutes` re-splits and keeps edited chunks whose text is unchanged. "
                    "Returns the chunk list, which are done / todo / invalid.",
     "inputSchema": {"type": "object", "properties": {"episode_dir": DIR,
                     "minutes": {"type": "number", "description": "Chunk length in minutes (min 3). Omit for the default (10); use a smaller value to retry after a failed chunk."},
                     "force": {"type": "boolean", "description": "Re-split even if nothing changed"}}, "required": ["episode_dir"]}},
    {"name": "merge_transcript",
     "description": "Check every work/chunks/NN.edited.md (stamps, length, marker balance) and join them into work/transcript.edited.md. "
                    "Returns ok false with the todo / invalid chunk numbers and reasons when a chunk must be redone.",
     "inputSchema": {"type": "object", "properties": {"episode_dir": DIR}, "required": ["episode_dir"]}},
    {"name": "episode_status",
     "description": "Where does the episode stand? Derived from the files in the episode folder: current step, done steps, next_action, chunk progress, pending human gate, open (deferred) gates. "
                    "Without episode_dir returns the most recently touched unfinished episode under the episodes root. Call it at the start of /video2aeo:episode and /video2aeo:resume, and after a crash.",
     "inputSchema": {"type": "object", "properties": {"episode_dir": DIR}}},
    {"name": "progress_note",
     "description": "Record an attempt, a failure or a deferred gate in work/progress.json. error: a step or chunk failed (counts an attempt, e.g. step \"chunk-03\"); ok: it succeeded; defer_gate: an unattended run continued past Gate A / the YouTube approval, which stay open.",
     "inputSchema": {"type": "object", "properties": {"episode_dir": DIR, "step": {"type": "string"}, "error": {"type": "string"},
                     "ok": {"type": "boolean"}, "defer_gate": {"type": "string", "enum": ["A", "youtube"]}}, "required": ["episode_dir", "step"]}},
    {"name": "render_package",
     "description": "Render work/episode.json into the requested outputs: youtube-description.txt, article.wp.html (Gutenberg) "
                    "+ wp-post-fields.json + work/schema.jsonld. Deterministic – never edit those files by hand; "
                    "edit episode.json and re-render.",
     "inputSchema": {"type": "object", "properties": {"episode_dir": DIR, "outputs": OUTPUTS}, "required": ["episode_dir"]}},
    {"name": "validate_package",
     "description": "Check YouTube limits, chapter rules, block markup, FAQ/schema parity, placeholders and number traceability for the "
                    "requested outputs. Writes work/review.md.",
     "inputSchema": {"type": "object", "properties": {"episode_dir": DIR, "outputs": OUTPUTS}, "required": ["episode_dir"]}},
    {"name": "wp_push_draft",
     "description": "Create or update the article in WordPress as a DRAFT (never publishes). Requires the article approval (gates.wordpress) and "
                    "~/.video2aeo/config.json. Only call when the user explicitly asks to push the draft.",
     "inputSchema": {"type": "object", "properties": {"episode_dir": DIR}, "required": ["episode_dir"]}},
]


GATED = {"get_video_info", "fetch_transcript", "import_transcript", "render_package", "validate_package",
         "wp_push_draft", "episode_path", "split_transcript", "merge_transcript", "episode_status", "progress_note"}
# Tools that write into an episode folder: it must sit in the episodes-root layout (or be an existing episode).
GUARDED = {"fetch_transcript", "import_transcript", "render_package", "validate_package", "wp_push_draft",
           "split_transcript", "merge_transcript", "progress_note"}
for _tool in TOOLS:
    if _tool["name"] in GUARDED:
        _tool["inputSchema"]["properties"]["allow_outside_root"] = {
            "type": "boolean", "description": "Only after the user explicitly confirmed an episode folder outside the episodes root"}


def _brand():
    return L.load_brand()


def call(name, args):
    if name == "setup_status":
        return L.setup_status()
    if name == "check_environment":
        return L.check_environment()
    if name == "save_setup":
        return L.save_setup(args.get("brand"), args.get("glossary"), args.get("guidelines_md"), args.get("guidelines_off"),
                            args.get("episodes_root"), args.get("models"))
    if name == "workspace_status":
        return L.classify_workspace(args.get("cwd") or None)
    if name in GATED:
        blocked = L.require_setup()
        if blocked:
            return blocked
    if name == "episode_status" and not args.get("episode_dir"):
        return P.find_unfinished() or {"ok": True, "step": "none", "message": "No unfinished episode under the episodes root."}
    if name in GUARDED or (name == "episode_status" and args.get("episode_dir")):
        wrong = L.check_episode_dir(args["episode_dir"], bool(args.get("allow_outside_root")))
        if wrong:
            return wrong
    if name == "split_transcript":
        return P.split_transcript(Path(args["episode_dir"]), args.get("minutes"), bool(args.get("force")))
    if name == "merge_transcript":
        return P.merge_transcript(Path(args["episode_dir"]))
    if name == "episode_status":
        return P.episode_status(Path(args["episode_dir"]))
    if name == "progress_note":
        return P.record_progress(Path(args["episode_dir"]), args["step"], args.get("error"), args.get("ok"), args.get("defer_gate"))
    if name == "episode_path":
        return L.episode_path(_brand(), args.get("format") or None, args.get("upload_date"), args["slug"], args.get("number"))
    if name == "get_video_info":
        info = N.video_info(args["url"])
        if isinstance(info, dict) and info.get("duration_seconds"):
            info["coverage"] = L.coverage_plan(info["duration_seconds"], L.resolve_format(_brand(), args.get("format")))
        return info
    if name == "fetch_transcript":
        return N.fetch_transcript(args["url"], Path(args["episode_dir"]), args.get("lang") or _brand().get("language", "bg"))
    if name == "import_transcript":
        segs = L.parse_transcript_text(Path(args["file"]).read_text(encoding="utf-8"))
        res = L.write_raw_transcript(segs, Path(args["episode_dir"]), f"import:{Path(args['file']).name}")
        if segs:  # last stamp = lower bound of the length; the video's duration (get_video_info) is preferred
            res["coverage"] = L.coverage_plan(segs[-1]["start"], L.resolve_format(_brand(), args.get("format")))
        return res
    d = Path(args["episode_dir"])
    outputs = args.get("outputs") or None
    if name == "render_package":
        return L.render_package(d, _brand(), outputs)
    if name == "validate_package":
        res = L.validate_package(d, _brand(), outputs)
        L.write_review(d, _brand(), res)
        return res
    if name == "wp_push_draft":
        return N.wp_create_draft(d, _brand())
    raise ValueError(f"Unknown tool {name}")


def handle(msg):
    mid, method = msg.get("id"), msg.get("method")
    if method == "initialize":
        pv = (msg.get("params") or {}).get("protocolVersion", "2025-06-18")
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": pv, "capabilities": {"tools": {}}, "serverInfo": SERVER}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        p = msg.get("params") or {}
        try:
            out = call(p["name"], p.get("arguments") or {})
            err = isinstance(out, dict) and out.get("ok") is False
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=2)}],
                "isError": bool(err and p["name"] not in ("validate_package", "workspace_status"))}}
        except Exception as ex:  # noqa: BLE001
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": f"{type(ex).__name__}: {ex}\n{traceback.format_exc()[-800:]}"}],
                "isError": True}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if mid is None:  # notification
        return None
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main():
    # MCP speaks UTF-8; Windows defaults to a legacy code page and would crash on the first Cyrillic character.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace" if stream is sys.stdin else "strict", newline="\n" if stream is sys.stdout else None)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            resp = handle(json.loads(line))
        except Exception as ex:  # noqa: BLE001
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(ex)}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
