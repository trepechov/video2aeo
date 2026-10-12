"""
yt-aeo core library (stdlib only).

Deterministic parts of the pipeline – the LLM never does these:
  * transcript parsing (YouTube "MM:SS text" paste, VTT, SRT, JSON segments)
  * rendering episode.json -> youtube-description.txt, article.wp.html, schema.jsonld
  * validation (YouTube limits, chapter rules, Gutenberg block balance, FAQ parity, placeholders)

Used by scripts/aeo.py (CLI) and server/server.py (local MCP tools).
"""
from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
# Per-user brand, glossary and credentials – never in the plugin. YT_AEO_HOME overrides it (used by the example checks).
USER_DIR = Path(os.environ.get("YT_AEO_HOME") or Path.home() / ".yt-aeo").expanduser()
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")
GENERIC_CHAPTERS = {
    "интро", "въведение", "начало", "разговор", "пазар", "съвети", "финал",
    "край", "заключение", "intro", "outro", "end", "start", "q&a", "въпроси",
}
YT_DESCRIPTION_LIMIT = 5000
YT_DESCRIPTION_MARGIN = 100

# ----------------------------------------------------------------------------
# config
# ----------------------------------------------------------------------------

def load_json(path: Path | str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_brand(override: Path | None = None) -> dict:
    """Generic plugin defaults, merged with ~/.yt-aeo/brand.json and then an explicit override file."""
    brand = load_json(PLUGIN_ROOT / "config" / "brand.json")
    for path in (USER_DIR / "brand.json", override):
        if path and Path(path).exists():
            brand = _deep_merge(brand, load_json(path))
    return brand


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
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "transcript.raw.json").write_text(
        json.dumps({"source": source, "segments": segs}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "transcript.raw.txt").write_text(segments_to_text(segs), encoding="utf-8")
    dur = segs[-1]["start"] if segs else 0
    return {"segments": len(segs), "last_timestamp": fmt_ts(dur), "words": sum(len(s["text"].split()) for s in segs),
            "files": ["transcript.raw.json", "transcript.raw.txt"], "source": source}

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

def render_description(ep: dict, brand: dict) -> str:
    vid = ep["video"]
    hours = (vid.get("duration_seconds") or 0) >= 3600
    out: list[str] = []
    out.append(plain(ep["answer_short"]).strip())
    if ep.get("context"):
        out += ["", plain(ep["context"]).strip()]
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
        who.append(f"🎙️ Водещ: {', '.join(host)}")
    if guests:
        who.append(f"👤 Гост: {', '.join(guests)}")
    if who:
        out += ["", *who]
    out += ["", brand["description"]["footer"].rstrip()]
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
    sponsor reads marked with <!-- sponsor --> ... <!-- /sponsor --> are dropped."""
    md_text = re.sub(r"<!--\s*sponsor\s*-->.*?<!--\s*/sponsor\s*-->", "", md_text, flags=re.S)
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
    org_node = {"@type": "Organization", "@id": org["url"].rstrip("/") + "/#organization", "name": org["name"],
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

def render_package(ep_dir: Path, brand: dict) -> dict:
    ep = load_json(ep_dir / "episode.json")
    tr_path = ep_dir / (ep.get("transcript_file") or "transcript.edited.md")
    transcript_md = tr_path.read_text(encoding="utf-8") if tr_path.exists() else None
    schema = render_schema(ep, brand)
    files = {
        "youtube-description.txt": render_description(ep, brand),
        "schema.jsonld": json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        "article.wp.html": render_article(ep, brand, transcript_md, schema),
    }
    for name, content in files.items():
        (ep_dir / name).write_text(content, encoding="utf-8")
    meta = {k: ep["article"].get(k) for k in ("seo_title", "slug", "meta_description", "focus_keyphrase", "category", "tags")}
    meta["title"] = ep["video"]["title"]
    meta["url"] = article_url(ep, brand)
    (ep_dir / "wp-post-fields.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"written": list(files) + ["wp-post-fields.json"], "description_chars": len(files["youtube-description.txt"]),
            "transcript_included": transcript_md is not None}

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


def validate_package(ep_dir: Path, brand: dict) -> dict:
    errors, warnings, placeholders = [], [], set()
    ep = load_json(ep_dir / "episode.json")
    # episode.json essentials
    for key in ("answer_short", "questions", "chapters", "faq", "article"):
        if not ep.get(key):
            errors.append(f"episode.json is missing '{key}'.")
    if len(re.findall(r"[.!?](\s|$)", ep.get("answer_short", ""))) > 4:
        warnings.append("answer_short is longer than ~3 sentences – keep it a direct answer.")
    if not (5 <= len(ep.get("questions", [])) <= 8):
        warnings.append("Aim for 5–8 questions in the mini-index.")
    if not (5 <= len(ep.get("faq", [])) <= 8):
        warnings.append("Aim for 5–8 FAQ entries.")
    e, w = validate_chapters(ep.get("chapters", []), ep["video"].get("duration_seconds"))
    errors += e
    warnings += w
    # description
    d_path = ep_dir / "youtube-description.txt"
    if d_path.exists():
        d = d_path.read_text(encoding="utf-8")
        placeholders |= set(PLACEHOLDER_RE.findall(d))
        if "<" in d or ">" in d:
            errors.append("YouTube description contains '<' or '>' – YouTube rejects these.")
        if len(d) > YT_DESCRIPTION_LIMIT:
            errors.append(f"Description is {len(d)} chars (limit {YT_DESCRIPTION_LIMIT}).")
        elif len(d) > YT_DESCRIPTION_LIMIT - YT_DESCRIPTION_MARGIN:
            warnings.append(f"Description is {len(d)} chars – under {YT_DESCRIPTION_MARGIN} chars of margin.")
        first = d.strip().split("\n", 1)[0]
        if len(first) < 80:
            warnings.append("Description should open with a 2–3 sentence direct answer.")
    else:
        errors.append("youtube-description.txt not rendered yet.")
    # article
    a_path = ep_dir / "article.wp.html"
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
    # schema
    s_path = ep_dir / "schema.jsonld"
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
        if (ep_dir / f).exists():
            corpus += (ep_dir / f).read_text(encoding="utf-8")
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
    return {"ok": not errors, "errors": errors, "warnings": warnings, "placeholders": sorted(placeholders)}


def review_sheet(ep_dir: Path, brand: dict, result: dict) -> str:
    ep = load_json(ep_dir / "episode.json")
    lines = [f"# Review – {ep['video']['title']}", "",
             f"**Status:** {'✅ ready for Gate B/C' if result['ok'] else '❌ fix errors first'}", ""]
    if result["errors"]:
        lines += ["## Errors (block publishing)", *[f"- {e}" for e in result["errors"]], ""]
    if result["warnings"]:
        lines += ["## Warnings", *[f"- {w}" for w in result["warnings"]], ""]
    if result["placeholders"]:
        lines += ["## Placeholders to fill", *[f"- `{p}`" for p in result["placeholders"]], ""]
    art = ep["article"]
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
              f"- [{'x' if g.get('A') else ' '}] Gate A – transcript, names, numbers, chapters {g.get('A') or ''}",
              f"- [{'x' if g.get('B') else ' '}] Gate B – copy & SEO fields {g.get('B') or ''}",
              f"- [{'x' if g.get('C') else ' '}] Gate C – compliance & publish go {g.get('C') or ''}", ""]
    return "\n".join(lines)
