"""
Network side of video2aeo (stdlib only). Runs on the marketer's own computer:
YouTube blocks caption requests from cloud IPs, so these calls must stay local.

  video_info(url)                       – title, channel, thumbnail, upload date, duration
  fetch_transcript(url, out_dir, lang)  – youtube-transcript-api -> yt-dlp -> clear error
  wp_create_draft(ep_dir, brand, cfg)   – WordPress REST, status=draft ONLY
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import aeo_lib as L

UA = {"User-Agent": "Mozilla/5.0 (video2aeo plugin)", "Accept-Language": "bg,en;q=0.8"}


def _get(url: str, headers: dict | None = None, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

# ----------------------------------------------------------------------------
# video metadata
# ----------------------------------------------------------------------------

def video_info(url: str) -> dict:
    vid = L.video_id_from_url(url)
    info = {"id": vid, "url": L.watch_url(vid)}
    try:
        o = json.loads(_get("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(info["url"])))
        info.update(title=o.get("title"), channel=o.get("author_name"), thumbnail_url=o.get("thumbnail_url"))
    except Exception as ex:  # noqa: BLE001
        info["oembed_error"] = str(ex)
    try:
        page = _get(info["url"]).decode("utf-8", "replace")
        m = re.search(r'"lengthSeconds":"(\d+)"', page)
        if m:
            info["duration_seconds"] = int(m.group(1))
        m = re.search(r'itemprop="uploadDate" content="([^"]+)"', page) or re.search(r'"uploadDate":"([^"]+)"', page)
        if m:
            info["upload_date"] = m.group(1)
        m = re.search(r'"shortDescription":"((?:[^"\\]|\\.)*)"', page)
        if m:
            info["current_description"] = json.loads('"' + m.group(1) + '"')
    except Exception as ex:  # noqa: BLE001
        info["page_error"] = str(ex)
    return info

# ----------------------------------------------------------------------------
# transcript
# ----------------------------------------------------------------------------

def _yt_cookie_args() -> list:
    """Optional yt-dlp cookie options from ~/.video2aeo/config.json: {"youtube": {"cookies_from_browser": "chrome"}} or
    {"youtube": {"cookies_file": "/path/cookies.txt"}}. Any logged-in YouTube account works – it only gets past the
    bot / IP checks; nothing is posted with it. Never put cookies in chat or in the repo."""
    try:
        cfg = json.loads((L.USER_DIR / "config.json").read_text(encoding="utf-8")).get("youtube", {})
    except (OSError, ValueError):
        return []
    if cfg.get("cookies_file"):
        return ["--cookies", str(Path(cfg["cookies_file"]).expanduser())]
    if cfg.get("cookies_from_browser"):
        return ["--cookies-from-browser", str(cfg["cookies_from_browser"])]
    return []


def fetch_transcript(url: str, out_dir: Path, lang: str = "bg") -> dict:
    vid = L.video_id_from_url(url)
    errors = []
    # 1) youtube-transcript-api (v1.x instance API, fallback to 0.x class API)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
        try:
            fetched = YouTubeTranscriptApi().fetch(vid, languages=[lang, "en"])
            raw = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else list(fetched)
        except AttributeError:
            raw = YouTubeTranscriptApi.get_transcript(vid, languages=[lang, "en"])  # type: ignore[attr-defined]
        segs = L._dedupe([{"start": float(s["start"]), "text": s["text"].replace("\n", " ").strip()} for s in raw])
        if segs:
            return L.write_raw_transcript(segs, out_dir, "youtube-transcript-api")
        errors.append("youtube-transcript-api returned no segments")
    except ImportError:
        errors.append("youtube-transcript-api not installed (pip install youtube-transcript-api)")
    except Exception as ex:  # noqa: BLE001
        errors.append(f"youtube-transcript-api: {type(ex).__name__}: {str(ex)[:300]}")
    # 2) yt-dlp, if present
    ytdlp = shutil.which("yt-dlp")
    if ytdlp:
        with tempfile.TemporaryDirectory() as tmp:
            cmd = [ytdlp, *_yt_cookie_args(), "--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", f"{lang}.*,{lang}",
                   "--sub-format", "vtt", "-o", os.path.join(tmp, "%(id)s.%(ext)s"), L.watch_url(vid)]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            vtts = sorted(Path(tmp).glob("*.vtt"))
            if vtts:
                segs = L.parse_transcript_text(vtts[0].read_text(encoding="utf-8"))
                return L.write_raw_transcript(segs, out_dir, f"yt-dlp:{vtts[0].name}")
            errors.append(f"yt-dlp: {res.stderr.strip()[-300:]}")
    else:
        errors.append("yt-dlp not found")
    return {"ok": False, "errors": errors,
            "fallback": "Automatic download failed (YouTube may be blocking this computer's IP, or yt-dlp is not "
                        "installed: brew install yt-dlp). Add the transcript by hand, any of: (1) YouTube Studio → "
                        "Subtitles → download .vtt/.srt; (2) the watch page → '…' → Show transcript → copy the text; "
                        "(3) an online YouTube-transcript service – paste the video address there and copy or "
                        "download the result. Save it as a .txt/.vtt/.srt file (or paste it in the chat), then call "
                        "import_transcript with the file."}

# ----------------------------------------------------------------------------
# WordPress draft
# ----------------------------------------------------------------------------

def _load_wp_config(path: Path | None) -> dict:
    candidates = [path] if path else []
    candidates.append(L.USER_DIR / "config.json")
    for c in candidates:
        if c and Path(c).exists():
            return json.loads(Path(c).read_text(encoding="utf-8")).get("wordpress", {})
    env = {k: os.environ.get(f"VIDEO2AEO_WP_{k.upper()}") for k in ("base_url", "username", "app_password")}
    return env if all(env.values()) else {}


def _wp(cfg: dict, method: str, path: str, body: dict | None = None, query: dict | None = None):
    url = cfg["base_url"].rstrip("/") + "/wp-json/wp/v2/" + path.lstrip("/")
    if query:
        url += "?" + urllib.parse.urlencode(query)
    token = base64.b64encode(f"{cfg['username']}:{cfg['app_password']}".encode()).decode()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        **UA, "Authorization": f"Basic {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as ex:
        raise RuntimeError(f"WordPress {method} {path}: HTTP {ex.code} {ex.read()[:300]!r}") from ex


def _term_ids(cfg: dict, taxonomy: str, names: list[str], create: bool) -> tuple[list[int], list[str]]:
    ids, missing = [], []
    for n in names:
        found = _wp(cfg, "GET", taxonomy, query={"search": n, "per_page": 20}) or []
        match = next((t for t in found if t["name"].strip().lower() == n.strip().lower()), None)
        if match:
            ids.append(match["id"])
        elif create:
            ids.append(_wp(cfg, "POST", taxonomy, {"name": n})["id"])
        else:
            missing.append(n)
    return ids, missing


def wp_create_draft(ep_dir: Path, brand: dict, cfg_path: Path | None = None) -> dict:
    cfg = _load_wp_config(cfg_path)
    if not cfg:
        return {"ok": False, "error": "No WordPress credentials. Create ~/.video2aeo/config.json with "
                                      "{\"wordpress\": {\"base_url\", \"username\", \"app_password\"}} (see setup skill)."}
    check = L.validate_package(ep_dir, brand, ["wordpress"])
    if not check["ok"]:
        return {"ok": False, "error": "Validation errors – fix before pushing.", "errors": check["errors"]}
    ep = L.load_episode(ep_dir)
    gates = ep.get("gates") or {}
    if not (gates.get("wordpress") or gates.get("B")):
        return {"ok": False, "error": "The article is not approved: sign it in episode.json → gates.wordpress "
                                      "(done by /video2aeo:wp-article after the editor's approval)."}
    art = ep["article"]
    cat_ids, missing_cats = _term_ids(cfg, "categories", [art["category"]] if art.get("category") else [], create=False)
    tag_ids, _ = _term_ids(cfg, "tags", art.get("tags", []), create=True)
    body = {"title": ep["video"]["title"], "content": (ep_dir / L.OUTPUT_FILES["wordpress"]).read_text(encoding="utf-8"),
            "status": "draft", "slug": art.get("slug"), "excerpt": art.get("meta_description", ""),
            "categories": cat_ids, "tags": tag_ids}
    state_file = L.find_work_file(ep_dir, "wp-result.json")
    post_id = L.load_json(state_file).get("id") if state_file.exists() else None
    if post_id:
        current = _wp(cfg, "GET", f"posts/{post_id}", query={"context": "edit"})
        if current.get("status") != "draft":
            return {"ok": False, "error": f"Post {post_id} is '{current.get('status')}', not a draft – "
                                          "will not overwrite. Edit it in WordPress."}
        post = _wp(cfg, "POST", f"posts/{post_id}", body)
    else:
        post = _wp(cfg, "POST", "posts", body)
    result = {"ok": True, "id": post["id"], "status": post["status"], "preview": post.get("link"),
              "edit": cfg["base_url"].rstrip("/") + f"/wp-admin/post.php?post={post['id']}&action=edit",
              "missing_categories": missing_cats,
              "manual": "Set SEO title / meta description / focus keyphrase in the SEO plugin panel (values in wp-post-fields.json)."}
    L.work_file(ep_dir, "wp-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
