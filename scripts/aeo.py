#!/usr/bin/env python3
"""
yt-aeo command line (same functions as the local MCP tools).

  python3 aeo.py transcript <youtube-url> <episode-dir> [--lang bg]   download subtitles
  python3 aeo.py import <transcript-file> <episode-dir>                 parse a pasted/uploaded transcript
  python3 aeo.py render <episode-dir> [--brand local-brand.json]       episode.json -> description, article, schema
  python3 aeo.py validate <episode-dir> [--brand ...]                   checks + review.md
  python3 aeo.py wp-draft <episode-dir> [--config ~/.yt-aeo/config.json]  push article as WordPress DRAFT
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aeo_lib as L  # noqa: E402
import aeo_net as N  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(prog="aeo")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("transcript"); t.add_argument("url"); t.add_argument("dir"); t.add_argument("--lang", default="bg")
    i = sub.add_parser("import"); i.add_argument("file"); i.add_argument("dir")
    for name in ("render", "validate"):
        s = sub.add_parser(name); s.add_argument("dir"); s.add_argument("--brand")
    w = sub.add_parser("wp-draft"); w.add_argument("dir"); w.add_argument("--config"); w.add_argument("--brand")
    m = sub.add_parser("info"); m.add_argument("url")
    a = p.parse_args(argv)

    if a.cmd == "info":
        out = N.video_info(a.url)
    elif a.cmd == "transcript":
        out = N.fetch_transcript(a.url, Path(a.dir), a.lang)
    elif a.cmd == "import":
        segs = L.parse_transcript_text(Path(a.file).read_text(encoding="utf-8"))
        out = L.write_raw_transcript(segs, Path(a.dir), f"import:{Path(a.file).name}")
    else:
        brand = L.load_brand(Path(a.brand) if a.brand else None)
        d = Path(a.dir)
        if a.cmd == "render":
            out = L.render_package(d, brand)
        elif a.cmd == "validate":
            out = L.validate_package(d, brand)
            (d / "review.md").write_text(L.review_sheet(d, brand, out), encoding="utf-8")
        else:
            out = N.wp_create_draft(d, brand, Path(a.config) if a.config else None)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
