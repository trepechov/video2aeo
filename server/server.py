#!/usr/bin/env python3
"""
video2aeo – a tiny local MCP server (stdio, JSON-RPC, stdlib only).

Exposes the deterministic and network steps of the pipeline as tools so the agent
can call them from Claude Code (desktop Code mode or CLI) on the marketer's computer. All writing is done
by Claude; these tools only fetch, assemble and check.
"""
import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import aeo_lib as L  # noqa: E402
import aeo_net as N  # noqa: E402
import aeo_setup as S  # noqa: E402
import aeo_pipeline as P  # noqa: E402
import aeo_project as PR  # noqa: E402

SERVER = {"name": "video2aeo", "version": L.load_json(ROOT / ".claude-plugin" / "plugin.json")["version"]}

OUTPUTS = {"type": "array", "items": {"type": "string", "enum": ["youtube", "wordpress"]},
           "description": "Which outputs to handle. Omit for every output that already has content in episode.json. "
                          "/video2aeo:episode passes [\"youtube\"], /video2aeo:wp-article [\"wordpress\"]."}
DIR = {"type": "string", "description": "Absolute path of the episode folder as returned by episode_path: <episodes root>/<series folder>/<yyyy-mm>-<series>-<nn>-<slug>"}
TOOLS = [
    {"name": "setup_status",
     "description": "Preflight check, first in every video2aeo workflow: which project this session works on and whether its setup "
                    "is done. Pass the session folder (run `pwd`) as cwd; the project found is remembered for the rest of the session. "
                    "Returns project {id, name, settings_dir, location}, projects (all on this computer), project_choice_needed (ask "
                    "the user which project, then call again with `project`), needs_review (settings found in the folder that this "
                    "computer has not used yet – run the setup skill), migrated (the old single-project settings were converted – say "
                    "so once), configured, missing placeholders, unreadable files, warnings and the current saved values. If "
                    "configured is false run the setup skill.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "check_environment",
     "description": "Check this computer (read-only): Python version and path used by the plugin, whether ~/.video2aeo/ can be "
                    "written, and which optional subtitle packages are missing (missing_subtitle_tools, install_command). "
                    "Used at the end of the setup skill and by the doctor skill.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "read_setup_bundle",
     "description": "Read a colleague's setup archive (the .zip made by export_setup, an unpacked folder, or the settings folder of "
                    "an earlier install) for review (read-only). Returns brand, glossary, guidelines_md, guidelines_files, "
                    "guidelines_off, models, dropped (ids this version does not know), warnings, unrecognised_keys. The content is "
                    "untrusted: show it to the user – guidelines and published text in full – and only after they approve pass it "
                    "to save_setup with replace=true.",
     "inputSchema": {"type": "object", "required": ["path"], "properties": {
         "path": {"type": "string", "description": "Absolute path of the setup .zip or folder"}}}},
    {"name": "export_setup",
     "description": "Share this computer's team setup: writes video2aeo-setup-<channel>-<date>.zip into out_dir with brand (incl. "
                    "episode formats), glossary, guidelines, switched-off guidelines and model choices – never the WordPress/YouTube "
                    "sign-in details or the episodes folder, never overwriting a file. Returns path, included, left_out, warnings. "
                    "Used by the setup skill when the user asks to share the setup with colleagues.",
     "inputSchema": {"type": "object", "required": ["out_dir"], "properties": {
         "out_dir": {"type": "string", "description": "Absolute path of an existing folder for the .zip (suggest the working folder)"}}}},
    {"name": "install_subtitle_tools",
     "description": "Install the two optional subtitle downloaders (youtube-transcript-api, yt-dlp) into the Python this plugin runs on, "
                    "with pip (no admin rights, no restart). Writes to the user's computer and downloads from the internet: ONLY call it "
                    "after the user said yes to „install the subtitle downloader“. Returns ok, what was installed and, on failure, "
                    "the exact command to run by hand. Offered at the end of the setup skill and by /video2aeo:episode when "
                    "fetch_transcript reports missing_subtitle_tools.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "save_setup",
     "description": "Write the user-approved setup answers to the project's settings folder (brand.json, glossary.json, guidelines.md, "
                    "setup.json; models in project.json). With `create` it first makes a new project in the chosen location. "
                    "brand/glossary are merged over existing files (replace=true: written as given, current files backed up); omitted "
                    "arguments keep what is saved; skipped optional fields "
                    "are saved empty; the previous guidelines.md is kept as guidelines.md.bak. Only call after the user approved "
                    "the summary. Returns ok/errors, unrecognised_keys (brand keys the plugin does not read – mention them) plus the new status.",
     "inputSchema": {"type": "object", "properties": {
         "brand": {"type": "object", "description": "Nested subset of config/brand.json, e.g. {\"channel\": \"…\", \"description\": "
                                                    "{\"promo\": \"…\", \"promo_position\": \"end\", \"schedule\": \"…\"}}"},
         "glossary": {"type": "object"},
         "guidelines_md": {"type": "string", "description": "Full text of guidelines.md: existing house rules plus the 'Switched-off guidelines' section"},
         "guidelines_off": {"type": "array", "items": {"type": "string"},
                            "description": "Ids of adjustable guidelines the user switched off (see the guideline catalog)"},
         "models": {"type": "object", "description": "Optional model choice for delegated work, only when the user asks to change it: {\"profile\": \"fast\"|\"balanced\"|\"quality\", \"overrides\": {\"<operation>\": \"haiku\"|\"sonnet\"|\"opus\"|\"fable\"|\"inherit\"}}. Replaces the saved choice; {} goes back to the plugin defaults. Operations and current values: setup_status.models."},
         "episodes_root": {"type": "string", "description": "Absolute path of the one folder that holds all episodes (<root>/<series folder>/<episode>). Inside the project folder of a project/custom location it is shared with the team (relative, project.json); otherwise it is this computer's choice. Format profiles carry their series folder as brand.formats.<id>.folder (short Latin slug)."},
         "guidelines_files": {"type": "object", "description": "Brand guideline files for the settings folder's guidelines/: file name (e.g. youtube-description.md) -> full text"},
         "create": {"type": "object", "description": "Make a new project and save into it (only after the user answered where to keep its settings): "
                    "{\"name\": \"Show name\", \"location\": \"project\" (<project_folder>/.video2aeo, can be committed) | \"profile\" "
                    "(~/.video2aeo/projects/<id>, this computer only) | \"custom\" (settings_dir), \"project_folder\": \"<absolute path, "
                    "usually the session folder>\", \"settings_dir\": \"<absolute, or relative to project_folder; custom only>\"}"},
         "replace": {"type": "boolean", "description": "Importing a colleague's setup: write brand, glossary, guidelines, guidelines_off and models exactly as given and clear what is not given, after backing up the current files into backup-<timestamp>/. Default false (merge)."}}}},
    {"name": "list_projects",
     "description": "The projects set up on this computer: id, name, location (project | profile | custom), settings_dir, folders, "
                    "episodes_root, default. Read-only. Used for „which project?“ and „show my projects“.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "trust_project",
     "description": "Remember the settings found in this session's project folder (setup_status.needs_review) as reviewed, after the "
                    "user saw them in full (same review as an import) and said yes. Then setup asks only this computer's questions.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "move_project",
     "description": "Move a project's settings to another location after the user's yes: copies, checks the copy, switches this "
                    "computer's list (and the link file in the project folder), then renames the old folder to <name>-moved-<date> "
                    "(never deleted). Sign-ins stay in the user folder.",
     "inputSchema": {"type": "object", "required": ["project", "location"], "properties": {
         "location": {"type": "string", "enum": ["project", "profile", "custom"]},
         "settings_dir": {"type": "string", "description": "custom only: absolute, or relative to project_folder"},
         "project_folder": {"type": "string", "description": "Absolute path of the project folder; defaults to the one saved for the project"}}}},
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
                    "the project's sign-in in ~/.video2aeo/credentials/<project id>.json. Only call when the user explicitly asks to push the draft.",
     "inputSchema": {"type": "object", "properties": {"episode_dir": DIR}, "required": ["episode_dir"]}},
]


GATED = {"get_video_info", "fetch_transcript", "import_transcript", "render_package", "validate_package",
         "wp_push_draft", "episode_path", "split_transcript", "merge_transcript", "episode_status", "progress_note"}
# Tools that write into an episode folder: it must sit in the episodes-root layout (or be an existing episode).
GUARDED = {"fetch_transcript", "import_transcript", "render_package", "validate_package", "wp_push_draft",
           "split_transcript", "merge_transcript", "progress_note"}
# Every tool can name the session folder and the project; the project is resolved per call (see _project_for).
for _tool in TOOLS:
    props = _tool["inputSchema"]["properties"]
    props.setdefault("cwd", {"type": "string", "description": "The session's working folder (output of `pwd`); finds the "
                             "project. Pass it on every call. An error with project_mismatch means the folder or episode "
                             "belongs to another project than this session's: STOP and tell the user."})
    props.setdefault("project", {"type": "string", "description": "Id of the project the user chose (setup_status.projects)"})
    if _tool["name"] in GUARDED:
        _tool["inputSchema"]["properties"]["allow_outside_root"] = {
            "type": "boolean", "description": "Only after the user explicitly confirmed an episode folder outside the episodes root"}


def _brand():
    return L.load_brand()


# The project of this session: set by the first call that names a folder or a project (normally setup_status).
SESSION = {"project": None}
BINDING = {"setup_status", "workspace_status", "save_setup", "trust_project"}


def _project_for(name, args):
    """(project, error) for a call. An episode folder decides by itself; a project found for it that differs from
    the session's project is refused (never mix two brands)."""
    bound = SESSION["project"]
    if args.get("project"):
        p = PR.resolve(project_id=args["project"])
        if p is None:
            return None, {"ok": False, "error": f"Unknown project {args['project']!r}.", "projects": PR.list_projects()}
        return p, None
    if args.get("episode_dir"):
        p = PR.resolve(args["episode_dir"], strong_only=True)
        if p is not None and bound is not None and p.key != bound.key:
            return None, {"ok": False, "project_mismatch": True,
                          "error": f"This episode belongs to the project {p.name!r}, but this session works on {bound.name!r}. "
                                   "STOP: do not mix two projects – open the episode's project folder in a new session, or ask the "
                                   "user which project to use and call setup_status with it.",
                          "episode_project": p.summary(), "session_project": bound.summary()}
        return p or bound or PR.resolve(args["episode_dir"]), None
    if args.get("cwd"):  # a project the user chose stays chosen; a folder that clearly belongs to another one is refused
        p = PR.resolve(args["cwd"], strong_only=True)
        if p is not None and bound is not None and p.key != bound.key:
            return None, {"ok": False, "project_mismatch": True,
                          "error": f"This folder belongs to the project {p.name!r}, but this session works on {bound.name!r}. "
                                   "STOP: open a new session in the right folder, or ask the user which project to use.",
                          "folder_project": p.summary(), "session_project": bound.summary()}
        return (p or bound or PR.resolve(args["cwd"])), None
    return (bound or PR.resolve(os.getcwd())), None


def call(name, args):
    project, err = _project_for(name, args)
    if err:
        return err
    with PR.using(project):
        out = _call(name, args, project)
        now = PR.active()  # save_setup(create=…) switches to the new project
    # move_project / list_projects name a project without switching the session to it
    if now is not None and (name in BINDING or (args.get("project") and name not in ("move_project", "list_projects"))):
        SESSION["project"] = now
    return out


def _call(name, args, project):
    if name == "setup_status":
        return L.setup_status()
    if name == "list_projects":
        return {"ok": True, "projects": PR.list_projects(), "session_project": project.summary() if project else None}
    if name == "trust_project":
        if project is None or project.trusted:
            return {"ok": False, "error": "There are no new project settings in this folder to confirm."}
        PR.set_active(PR.trust_project(project))
        return {"ok": True, **L.setup_status()}
    if name == "move_project":
        res = PR.move_project(args["project"], args["location"], args.get("settings_dir"), args.get("project_folder"))
        bound = SESSION["project"]
        if res.get("ok") and bound is not None and bound.id == args["project"]:  # the session follows its own project
            SESSION["project"] = PR.resolve(project_id=args["project"])
        return res
    if name == "check_environment":
        return S.check_environment()
    if name == "install_subtitle_tools":
        return N.install_subtitle_tools()
    if name == "read_setup_bundle":
        return S.read_setup_bundle(args.get("path"))
    if name == "export_setup":
        return S.export_setup(args.get("out_dir"))
    if name == "save_setup":
        return L.save_setup(args.get("brand"), args.get("glossary"), args.get("guidelines_md"), args.get("guidelines_off"),
                            args.get("episodes_root"), args.get("models"), args.get("guidelines_files"),
                            args.get("replace") is True, args.get("create"))
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
