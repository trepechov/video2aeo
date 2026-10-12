#!/usr/bin/env python3
"""
yt-aeo-tools – a tiny local MCP server (stdio, JSON-RPC, stdlib only).

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

SERVER = {"name": "yt-aeo-tools", "version": "0.1.0"}

DIR = {"type": "string", "description": "Absolute path of the episode folder, e.g. …/episodes/2026-10-dk-08-danatsi"}
TOOLS = [
    {"name": "get_video_info",
     "description": "Get title, channel, thumbnail, upload date, duration and the current description of a YouTube video.",
     "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "fetch_transcript",
     "description": "Download the video's subtitles (Bulgarian by default) from YouTube to transcript.raw.json/.txt in the episode folder. "
                    "Runs on this computer. On failure returns the manual fallback.",
     "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "episode_dir": DIR,
                                                       "lang": {"type": "string", "default": "bg"}},
                     "required": ["url", "episode_dir"]}},
    {"name": "import_transcript",
     "description": "Parse a transcript file the user downloaded or pasted (VTT, SRT, YouTube 'MM:SS text' copy, JSON) into transcript.raw.*",
     "inputSchema": {"type": "object", "properties": {"file": {"type": "string"}, "episode_dir": DIR},
                     "required": ["file", "episode_dir"]}},
    {"name": "render_package",
     "description": "Render episode.json (+ transcript.edited.md) into youtube-description.txt, article.wp.html (Gutenberg), "
                    "schema.jsonld and wp-post-fields.json. Deterministic – never edit those files by hand; edit episode.json and re-render.",
     "inputSchema": {"type": "object", "properties": {"episode_dir": DIR}, "required": ["episode_dir"]}},
    {"name": "validate_package",
     "description": "Check YouTube limits, chapter rules, block markup, FAQ/schema parity, placeholders and number traceability. Writes review.md.",
     "inputSchema": {"type": "object", "properties": {"episode_dir": DIR}, "required": ["episode_dir"]}},
    {"name": "wp_push_draft",
     "description": "Create or update the article in WordPress as a DRAFT (never publishes). Requires Gate B signed and "
                    "~/.yt-aeo/config.json. Only call when the user explicitly asks to push the draft.",
     "inputSchema": {"type": "object", "properties": {"episode_dir": DIR}, "required": ["episode_dir"]}},
]


def _brand():
    return L.load_brand()


def call(name, args):
    if name == "get_video_info":
        return N.video_info(args["url"])
    if name == "fetch_transcript":
        return N.fetch_transcript(args["url"], Path(args["episode_dir"]), args.get("lang", "bg"))
    if name == "import_transcript":
        segs = L.parse_transcript_text(Path(args["file"]).read_text(encoding="utf-8"))
        return L.write_raw_transcript(segs, Path(args["episode_dir"]), f"import:{Path(args['file']).name}")
    d = Path(args["episode_dir"])
    if name == "render_package":
        return L.render_package(d, _brand())
    if name == "validate_package":
        res = L.validate_package(d, _brand())
        (d / "review.md").write_text(L.review_sheet(d, _brand(), res), encoding="utf-8")
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
                "isError": bool(err and p["name"] != "validate_package")}}
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
