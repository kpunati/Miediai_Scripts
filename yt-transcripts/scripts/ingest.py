"""scripts/ingest.py — pull metadata + transcript for a YouTube channel or video URL.

See operations/ingest/INSTRUCTIONS.md for the canonical spec.

Usage:
  python scripts/ingest.py <url>                  # auto-detect channel vs video
  python scripts/ingest.py --video <url>          # force video
  python scripts/ingest.py --channel <url>        # force channel
  python scripts/ingest.py --from-sources         # process every channel in config/sources.csv
  python scripts/ingest.py --dry-run              # don't write, just report

External dependencies:
  - yt-dlp (CLI, on PATH)               REQUIRED
  - ffmpeg                              required only if a video needs the Whisper fallback
  - faster-whisper                      required only if a video needs the Whisper fallback
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output" / "by-channel"
SOURCES_CSV = REPO_ROOT / "config" / "sources.csv"
LOG_DIR = REPO_ROOT / "logs"

TARGET_PARA_SEC = 30
HARD_MAX_PARA_SEC = 60
UNPUNCTUATED_FALLBACK_RATIO = 0.5
DEFAULT_CONCURRENCY = 3  # parallel yt-dlp workers; >5 risks YouTube 429 rate-limiting

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"ingestion-{dt.date.today().isoformat()}.log"
    logger = logging.getLogger("ingest")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(log_path, mode="a")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


# ---------------------------------------------------------------------------
# yt-dlp wrappers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def yt_dlp_version() -> str:
    r = _run(["yt-dlp", "--version"])
    return r.stdout.strip() if r.returncode == 0 else "(not installed)"


def fetch_metadata(url: str) -> dict:
    r = _run(["yt-dlp", "--dump-json", "--skip-download", url])
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp metadata fetch failed: {r.stderr.strip()[:400]}")
    return json.loads(r.stdout)


def fetch_captions_vtt(video_id: str, video_url: str, tmpdir: Path) -> tuple[str, str] | None:
    """Return (source, vtt_content) or None if no captions available.

    source is one of: 'manual_captions', 'auto_captions'.
    Prefers manual; falls back to auto.
    """
    # Try manual first
    for source, flag in (("manual_captions", "--write-subs"), ("auto_captions", "--write-auto-subs")):
        cmd = [
            "yt-dlp",
            flag,
            "--skip-download",
            "--sub-format", "vtt",
            "--sub-langs", "en.*,en",
            "-o", str(tmpdir / "%(id)s"),
            video_url,
        ]
        r = _run(cmd)
        if r.returncode != 0:
            continue
        # Find any .vtt that yt-dlp dropped
        vtts = sorted(tmpdir.glob(f"{video_id}*.vtt"))
        if vtts:
            content = vtts[0].read_text()
            # Clean up so the next attempt has a clean slate
            for v in vtts:
                v.unlink(missing_ok=True)
            return source, content
    return None


def enumerate_channel(channel_url: str) -> list[dict]:
    """Return a list of {id, title, duration} dicts for videos on the channel.

    Uses --flat-playlist (fast — no per-video metadata fetch).
    Returned items don't include publish dates; the per-video metadata pass adds those.
    """
    cmd = ["yt-dlp", "--flat-playlist", "--dump-json", channel_url]
    r = _run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"channel enumeration failed: {r.stderr.strip()[:400]}")
    items = []
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items


# ---------------------------------------------------------------------------
# VTT parsing
# ---------------------------------------------------------------------------

SENTENCE_END_RE = re.compile(r"[.!?][\"')\]]*\s*$")


def parse_vtt(vtt_content: str) -> list[tuple[str, str]]:
    """Parse VTT into [(HH:MM:SS, text), ...].

    Two formats handled:
    - YouTube rolling auto-captions: each cue has a carry-over text line plus a
      <c>-tagged "new content" line. We detect this format (any `<c>` in file)
      and STRICTLY keep only cues with <c> tags — carry-over cues duplicate the
      prior cue's content and must be skipped.
    - Plain VTT / SRT-converted-to-VTT (typical of manual captions): no <c>
      tags anywhere. Concatenate non-empty text lines per cue.
    """
    is_rolling = "<c>" in vtt_content
    blocks = re.split(r"\n\n+", vtt_content)
    cues: list[tuple[str, str]] = []
    for b in blocks:
        if "WEBVTT" in b or b.strip().startswith(("Kind:", "Language:")) or not b.strip():
            continue
        lines = b.strip().split("\n")
        ts_match = re.match(r"(\d{2}):(\d{2}):(\d{2})\.\d+\s+-->\s+", lines[0])
        if not ts_match:
            continue
        h, m, s = ts_match.groups()
        start = f"{h}:{m}:{s}"

        if is_rolling:
            text_line = next((l for l in lines[1:] if "<c>" in l), None)
            if text_line is None:
                continue  # carry-over cue — duplicate of previous, skip
        else:
            text_line = " ".join(l for l in lines[1:] if l.strip())
            if not text_line:
                continue

        text = re.sub(r"<\d{2}:\d{2}:\d{2}\.\d+>", "", text_line)
        text = re.sub(r"</?c[^>]*>", "", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            cues.append((start, text))
    return cues


def _ts_to_sec(ts: str) -> int:
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def group_paragraphs(cues: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], int]:
    """Sentence-aware grouping with HARD_MAX_PARA_SEC fallback.

    Returns (paragraphs, fallback_use_count).
    """
    paragraphs: list[tuple[str, str]] = []
    fallback_uses = 0
    if not cues:
        return paragraphs, 0

    i = 0
    while i < len(cues):
        para_start = cues[i][0]
        para_start_sec = _ts_to_sec(para_start)
        parts: list[str] = []
        used_fallback = False
        while i < len(cues):
            ts, text = cues[i]
            sec = _ts_to_sec(ts)
            parts.append(text)
            i += 1
            joined = " ".join(parts)
            elapsed = sec - para_start_sec
            if elapsed >= TARGET_PARA_SEC and SENTENCE_END_RE.search(joined):
                break
            if elapsed >= HARD_MAX_PARA_SEC:
                used_fallback = True
                break
        if used_fallback:
            fallback_uses += 1
        paragraphs.append((para_start, " ".join(parts)))
    return paragraphs, fallback_uses


# ---------------------------------------------------------------------------
# Whisper fallback (optional)
# ---------------------------------------------------------------------------

def whisper_available() -> bool:
    if not shutil.which("ffmpeg"):
        return False
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def whisper_transcribe(video_url: str, video_id: str, tmpdir: Path) -> list[tuple[str, str]]:
    """Run Whisper on a video's audio. Returns timestamped cues like parse_vtt."""
    from faster_whisper import WhisperModel  # type: ignore

    audio_path = tmpdir / f"{video_id}.m4a"
    cmd = [
        "yt-dlp",
        "-f", "bestaudio[ext=m4a]/bestaudio",
        "-o", str(audio_path),
        video_url,
    ]
    r = _run(cmd)
    if r.returncode != 0 or not audio_path.exists():
        raise RuntimeError(f"audio download failed: {r.stderr.strip()[:400]}")
    try:
        model = WhisperModel("medium", compute_type="auto")
        segments, _ = model.transcribe(str(audio_path), beam_size=5)
        cues: list[tuple[str, str]] = []
        for seg in segments:
            sec = int(seg.start)
            h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
            ts = f"{h:02d}:{m:02d}:{s:02d}"
            cues.append((ts, seg.text.strip()))
        return cues
    finally:
        audio_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Channel slug derivation + sources.csv handling
# ---------------------------------------------------------------------------

def derive_slug(uploader_id: str | None, channel_name: str) -> str:
    """Prefer @handle (stripped of @). Else slugify channel_name. Lowercase, hyphens only."""
    if uploader_id and uploader_id.startswith("@"):
        candidate = uploader_id[1:]
    else:
        candidate = channel_name or "unknown"
    slug = re.sub(r"[^a-z0-9]+", "-", candidate.lower()).strip("-")
    return slug or "unknown"


@dataclass
class ChannelConfig:
    channel_url: str
    channel_slug: str
    exclude_shorts: bool
    min_duration_sec: int
    since_date: dt.date | None
    notes: str


def load_sources() -> list[ChannelConfig]:
    if not SOURCES_CSV.exists():
        return []
    rows: list[ChannelConfig] = []
    with SOURCES_CSV.open(newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if not r.get("channel_url"):
                continue
            try:
                sd = dt.date.fromisoformat(r["since_date"]) if r.get("since_date") else None
            except ValueError:
                sd = None
            rows.append(ChannelConfig(
                channel_url=r["channel_url"].strip(),
                channel_slug=(r.get("channel_slug") or "").strip(),
                exclude_shorts=(r.get("exclude_shorts") or "true").strip().lower() == "true",
                min_duration_sec=int(r.get("min_duration_sec") or 90),
                since_date=sd,
                notes=(r.get("notes") or "").strip(),
            ))
    return rows


def find_channel_config(slug: str) -> ChannelConfig | None:
    for c in load_sources():
        if c.channel_slug == slug:
            return c
    return None


def append_channel_to_sources(cfg: ChannelConfig) -> None:
    write_header = not SOURCES_CSV.exists() or SOURCES_CSV.stat().st_size == 0
    with SOURCES_CSV.open("a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["channel_url", "channel_slug", "exclude_shorts", "min_duration_sec", "since_date", "notes"])
        w.writerow([
            cfg.channel_url,
            cfg.channel_slug,
            str(cfg.exclude_shorts).lower(),
            cfg.min_duration_sec,
            cfg.since_date.isoformat() if cfg.since_date else "",
            cfg.notes,
        ])


# ---------------------------------------------------------------------------
# YAML rendering (matches the hand-build format)
# ---------------------------------------------------------------------------

def _yq(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _yblock(s: str, indent: int = 2) -> str:
    pad = " " * indent
    lines = s.split("\n")
    return "|\n" + "\n".join(pad + line if line else "" for line in lines)


def _ylist(items: list[str]) -> str:
    if not items:
        return "[]"
    return "[" + ", ".join(_yq(x) for x in items) + "]"


def render_frontmatter(meta: dict, *, transcript_source: str, ingest_date: dt.date, flags: list[str]) -> str:
    upload = meta["upload_date"]  # YYYYMMDD
    publish_date = f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}"
    duration_seconds = int(meta["duration"])
    mins, secs = divmod(duration_seconds, 60)
    duration_human = f"{mins}:{secs:02d}"
    language = (meta.get("language") or "en").split("-")[0]
    tags = meta.get("tags") or []
    description = meta.get("description") or ""
    channel_slug = derive_slug(meta.get("uploader_id"), meta.get("channel", ""))

    return (
        "---\n"
        "# === Identifiers (immutable) ===\n"
        f'video_id: "{meta["id"]}"\n'
        f'url: "https://youtube.com/watch?v={meta["id"]}"\n'
        "\n"
        "# === Core metadata ===\n"
        f"title: {_yq(meta['title'])}\n"
        f"channel_name: {_yq(meta['channel'])}\n"
        f'channel_id: "{meta["channel_id"]}"\n'
        f'channel_slug: "{channel_slug}"\n'
        f"publish_date: {publish_date}\n"
        f"duration_seconds: {duration_seconds}\n"
        f'duration_human: "{duration_human}"\n'
        f"view_count_at_ingest: {int(meta.get('view_count') or 0)}\n"
        f'language: "{language}"\n'
        "\n"
        "# === Original content (verbatim) ===\n"
        f"description: {_yblock(description, indent=2)}\n"
        f"tags_youtube: {_ylist(tags)}\n"
        "\n"
        "# === Transcript provenance ===\n"
        f'transcript_source: "{transcript_source}"\n'
        "transcript_has_timestamps: true\n"
        f"ingest_date: {ingest_date.isoformat()}\n"
        "ingest_version: 1\n"
        "\n"
        "# === Enrichment state (empty at ingest) ===\n"
        "enriched: false\n"
        "enrichment_date: null\n"
        "enrichment_version: null\n"
        'summary: ""\n'
        "topics: []\n"
        "topics_proposed: []\n"
        "entities:\n"
        "  people: []\n"
        "  companies: []\n"
        "  tickers: []\n"
        "  funds: []\n"
        "  products: []\n"
        "  concepts: []\n"
        'content_type: ""\n'
        'audience_level: ""\n'
        "key_claims: []\n"
        "tags_topic: []\n"
        "\n"
        "# === Governance ===\n"
        'usage_policy: "research_only"\n'
        f"flags: {_ylist(flags)}\n"
        'notes: ""\n'
        "---\n"
    )


def render_body(meta: dict, paragraphs: list[tuple[str, str]]) -> str:
    upload = meta["upload_date"]
    publish_date = f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}"
    duration_seconds = int(meta["duration"])
    mins, secs = divmod(duration_seconds, 60)
    duration_human = f"{mins}:{secs:02d}"

    lines = [
        f"\n# {meta['title']}",
        "",
        f"**Channel:** {meta['channel']}",
        f"**Published:** {publish_date}",
        f"**URL:** https://youtube.com/watch?v={meta['id']}",
        f"**Duration:** {duration_human}",
        "",
        "## Transcript",
        "",
    ]
    for ts, text in paragraphs:
        lines.append(f"[{ts}] {text}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-video processing
# ---------------------------------------------------------------------------

@dataclass
class IngestResult:
    status: str  # 'success' | 'skip:exists' | 'skip:filtered' | 'fail:<reason>'
    path: Path | None = None
    source: str | None = None
    duration_seconds: int | None = None
    processing_seconds: float = 0.0
    fallback_uses: int = 0
    total_paragraphs: int = 0


def video_filename(channel_slug: str, publish_date: str, video_id: str) -> str:
    return f"{channel_slug}_{publish_date}_{video_id}.md"


def output_path_for(channel_slug: str, publish_date: str, video_id: str) -> Path:
    return OUTPUT_DIR / channel_slug / video_filename(channel_slug, publish_date, video_id)


def passes_filters(meta: dict, cfg: ChannelConfig | None) -> tuple[bool, str]:
    duration = int(meta.get("duration") or 0)
    if cfg is None:
        cfg = ChannelConfig(channel_url="", channel_slug="", exclude_shorts=True, min_duration_sec=90, since_date=None, notes="")
    if cfg.exclude_shorts and duration < 60:
        return False, "shorts/duration_lt_60"
    if duration < cfg.min_duration_sec:
        return False, f"duration_lt_{cfg.min_duration_sec}"
    if cfg.since_date:
        try:
            upload = dt.date.fromisoformat(f"{meta['upload_date'][:4]}-{meta['upload_date'][4:6]}-{meta['upload_date'][6:8]}")
            if upload < cfg.since_date:
                return False, f"before_since_date_{cfg.since_date}"
        except (KeyError, ValueError):
            pass
    return True, ""


def process_video(
    video_url: str,
    *,
    cfg: ChannelConfig | None,
    logger: logging.Logger,
    dry_run: bool = False,
    apply_filters: bool = True,
) -> IngestResult:
    t0 = dt.datetime.now()
    try:
        meta = fetch_metadata(video_url)
    except Exception as e:
        logger.warning(f"fetch_metadata failed for {video_url}: {e}")
        return IngestResult(status=f"fail:metadata:{e}")

    video_id = meta["id"]
    upload = meta["upload_date"]
    publish_date = f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}"
    channel_slug = derive_slug(meta.get("uploader_id"), meta.get("channel", ""))
    out_path = output_path_for(channel_slug, publish_date, video_id)

    # Idempotency
    if out_path.exists():
        logger.info(f"{video_id} status=skip:exists")
        return IngestResult(status="skip:exists", path=out_path)

    # Filters apply only when invoked from a channel enumeration (the user
    # explicitly named this video on the CLI, so they are the curator).
    if apply_filters:
        ok, reason = passes_filters(meta, cfg)
        if not ok:
            logger.info(f"{video_id} status=skip:filtered reason={reason}")
            return IngestResult(status=f"skip:filtered:{reason}", duration_seconds=int(meta.get("duration") or 0))

    # Captions
    with tempfile.TemporaryDirectory() as tdir_str:
        tmpdir = Path(tdir_str)
        captions = fetch_captions_vtt(video_id, video_url, tmpdir)
        if captions is not None:
            transcript_source, vtt = captions
            cues = parse_vtt(vtt)
        elif whisper_available():
            transcript_source = "whisper"
            try:
                cues = whisper_transcribe(video_url, video_id, tmpdir)
            except Exception as e:
                logger.warning(f"{video_id} whisper failed: {e}")
                return IngestResult(status=f"fail:whisper:{e}", duration_seconds=int(meta["duration"]))
        else:
            logger.warning(f"{video_id} status=skip:no_captions_whisper_unavailable")
            return IngestResult(status="skip:no_captions_whisper_unavailable", duration_seconds=int(meta["duration"]))

    if not cues:
        return IngestResult(status="fail:no_cues_after_parse")

    paragraphs, fallback_uses = group_paragraphs(cues)
    flags: list[str] = []
    if paragraphs:
        ratio = fallback_uses / len(paragraphs)
        if ratio > UNPUNCTUATED_FALLBACK_RATIO:
            flags.append("unpunctuated_captions")
    if transcript_source == "whisper":
        flags.append("whisper_review_needed")

    fm = render_frontmatter(meta, transcript_source=transcript_source, ingest_date=dt.date.today(), flags=flags)
    body = render_body(meta, paragraphs)
    content = fm + body

    if dry_run:
        logger.info(f"{video_id} status=dry_run path={out_path.relative_to(REPO_ROOT)}")
        return IngestResult(status="dry_run", path=out_path, source=transcript_source, fallback_uses=fallback_uses, total_paragraphs=len(paragraphs))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content)
    elapsed = (dt.datetime.now() - t0).total_seconds()
    logger.info(
        f"{video_id} status=success source={transcript_source} duration={meta['duration']}s "
        f"processed_in={elapsed:.1f}s paragraphs={len(paragraphs)} fallback={fallback_uses}"
    )
    return IngestResult(
        status="success", path=out_path, source=transcript_source,
        duration_seconds=int(meta["duration"]), processing_seconds=elapsed,
        fallback_uses=fallback_uses, total_paragraphs=len(paragraphs),
    )


# ---------------------------------------------------------------------------
# URL detection + channel flow
# ---------------------------------------------------------------------------

def detect_url_type(url: str) -> str:
    if "watch?v=" in url or "youtu.be/" in url or "/shorts/" in url:
        return "video"
    if re.search(r"/(@[^/]+|channel/UC[A-Za-z0-9_-]+|c/[^/]+|user/[^/]+)/?", url):
        return "channel"
    return "unknown"


def _channel_slug_from_url(channel_url: str) -> str | None:
    """Extract handle slug from URLs like https://youtube.com/@iShares or /c/Name."""
    m = re.search(r"/@([^/?#]+)", channel_url)
    if m:
        return re.sub(r"[^a-z0-9]+", "-", m.group(1).lower()).strip("-") or None
    return None


def process_channel(channel_url: str, *, logger: logging.Logger, dry_run: bool = False, concurrency: int = DEFAULT_CONCURRENCY) -> dict:
    # Enumerate first (handles JSON-lines correctly). Use first item's uploader info to
    # derive slug if the URL doesn't have a @handle.
    items = enumerate_channel(channel_url)
    if not items:
        raise RuntimeError(f"no videos found at {channel_url}")
    slug = _channel_slug_from_url(channel_url) or derive_slug(
        items[0].get("uploader_id") or items[0].get("uploader"),
        items[0].get("channel") or items[0].get("uploader") or "",
    )
    channel_display = items[0].get("channel") or items[0].get("uploader") or slug

    cfg = find_channel_config(slug)
    if cfg is None:
        cfg = ChannelConfig(
            channel_url=channel_url,
            channel_slug=slug,
            exclude_shorts=True,
            min_duration_sec=90,
            since_date=dt.date.today().replace(year=dt.date.today().year - 3),
            notes=str(channel_display).strip(),
        )
        logger.info(f"channel {slug} not in sources.csv — appending with defaults")
        if not dry_run:
            append_channel_to_sources(cfg)

    logger.info(f"channel {slug}: {len(items)} videos in uploads (concurrency={concurrency})")

    stats = {"success": 0, "skip": 0, "fail": 0, "total": len(items)}
    completed = 0

    def _worker(it: dict) -> IngestResult:
        vid_url = it.get("url") or f"https://www.youtube.com/watch?v={it.get('id')}"
        return process_video(vid_url, cfg=cfg, logger=logger, dry_run=dry_run, apply_filters=True)

    # GIL serializes the integer increments; no lock needed.
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        futures = [ex.submit(_worker, it) for it in items]
        for fut in as_completed(futures):
            try:
                res = fut.result()
            except Exception as e:
                logger.error(f"worker raised: {e}")
                stats["fail"] += 1
                completed += 1
                continue
            if res.status.startswith("success") or res.status == "dry_run":
                stats["success"] += 1
            elif res.status.startswith("skip"):
                stats["skip"] += 1
            else:
                stats["fail"] += 1
            completed += 1
            if completed % 10 == 0 or completed == len(items):
                logger.info(f"progress: {completed}/{len(items)} ({stats})")
    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a YouTube channel or video into the catalog.")
    parser.add_argument("url", nargs="?", help="channel or video URL")
    parser.add_argument("--video", help="explicit video URL")
    parser.add_argument("--channel", help="explicit channel URL")
    parser.add_argument("--from-sources", action="store_true", help="process every channel in config/sources.csv")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help=f"parallel workers for channel runs (default: {DEFAULT_CONCURRENCY}; >5 risks rate-limiting)")
    args = parser.parse_args()

    logger = _setup_logging()
    logger.info(f"yt-dlp version: {yt_dlp_version()}")

    if args.from_sources:
        for cfg in load_sources():
            logger.info(f"=== {cfg.channel_slug} ({cfg.channel_url}) ===")
            try:
                stats = process_channel(cfg.channel_url, logger=logger, dry_run=args.dry_run, concurrency=args.concurrency)
                logger.info(f"channel {cfg.channel_slug}: {stats}")
            except Exception as e:
                logger.error(f"channel {cfg.channel_slug} failed: {e}")
        return 0

    target = args.video or args.channel or args.url
    if not target:
        parser.print_help()
        return 2

    if args.video:
        kind = "video"
    elif args.channel:
        kind = "channel"
    else:
        kind = detect_url_type(target)

    if kind == "video":
        # Look up channel config by detecting slug via metadata
        meta = fetch_metadata(target)
        slug = derive_slug(meta.get("uploader_id"), meta.get("channel", ""))
        cfg = find_channel_config(slug)
        if cfg is None:
            logger.info(f"channel {slug} not in sources.csv — appending with defaults")
            cfg = ChannelConfig(
                channel_url=f"https://youtube.com/{(meta.get('uploader_id') or '@' + slug)}",
                channel_slug=slug,
                exclude_shorts=True,
                min_duration_sec=90,
                since_date=dt.date.today().replace(year=dt.date.today().year - 3),
                notes=meta.get("channel", "").strip(),
            )
            if not args.dry_run:
                append_channel_to_sources(cfg)
        res = process_video(target, cfg=cfg, logger=logger, dry_run=args.dry_run, apply_filters=False)
        logger.info(f"result: {res.status} path={res.path}")
        return 0 if res.status in ("success", "dry_run") or res.status.startswith("skip") else 1
    elif kind == "channel":
        stats = process_channel(target, logger=logger, dry_run=args.dry_run, concurrency=args.concurrency)
        logger.info(f"channel result: {stats}")
        return 0
    else:
        logger.error(f"could not detect URL type: {target}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
