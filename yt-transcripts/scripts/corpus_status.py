"""scripts/corpus_status.py — dashboard report on the catalog.

See operations/status/INSTRUCTIONS.md for the canonical spec (sections, ordering).
Read-only.

Usage:
  python scripts/corpus_status.py           # full human-readable report
  python scripts/corpus_status.py --json    # machine-readable JSON
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import frontmatter

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output" / "by-channel"


def _date(value):
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            return None
    return None


def collect_stats() -> dict:
    if not OUTPUT_DIR.exists():
        return {"total": 0, "files": []}

    files = sorted(OUTPUT_DIR.rglob("*.md"))
    by_channel = defaultdict(list)
    by_source = Counter()
    by_content_type = Counter()
    by_audience = Counter()
    flags_counter = Counter()
    proposed_topics_counter = Counter()
    topics_counter = Counter()
    enrichment_versions = Counter()
    enriched_count = 0
    total_duration_sec = 0
    publish_dates: list[dt.date] = []
    ingest_dates: list[dt.date] = []
    parse_failures: list[str] = []

    recent_records: list[tuple[dt.date, str, str, str]] = []

    for fp in files:
        try:
            post = frontmatter.load(fp)
        except Exception as e:
            parse_failures.append(f"{fp.relative_to(REPO_ROOT)}: {e}")
            continue
        m = post.metadata
        slug = m.get("channel_slug", "(unknown)")
        by_channel[slug].append(m)
        by_source[m.get("transcript_source", "(unset)")] += 1
        total_duration_sec += int(m.get("duration_seconds") or 0)

        pd = _date(m.get("publish_date"))
        if pd:
            publish_dates.append(pd)
        id_ = _date(m.get("ingest_date"))
        if id_:
            ingest_dates.append(id_)
            if (dt.date.today() - id_).days <= 7:
                recent_records.append((id_, m.get("video_id", ""), slug, m.get("title", "")))

        for fl in m.get("flags") or []:
            flags_counter[fl] += 1
        for t in m.get("topics_proposed") or []:
            proposed_topics_counter[t] += 1
        for t in m.get("topics") or []:
            topics_counter[t] += 1

        if m.get("enriched"):
            enriched_count += 1
            by_content_type[m.get("content_type") or "(unset)"] += 1
            by_audience[m.get("audience_level") or "(unset)"] += 1
            ev = m.get("enrichment_version")
            if ev is not None:
                enrichment_versions[ev] += 1

    return {
        "total": len(files),
        "parse_failures": parse_failures,
        "by_channel": by_channel,
        "by_source": by_source,
        "by_content_type": by_content_type,
        "by_audience": by_audience,
        "flags_counter": flags_counter,
        "proposed_topics_counter": proposed_topics_counter,
        "topics_counter": topics_counter,
        "enrichment_versions": enrichment_versions,
        "enriched_count": enriched_count,
        "total_duration_sec": total_duration_sec,
        "publish_dates": publish_dates,
        "ingest_dates": ingest_dates,
        "recent_records": recent_records,
    }


def _fmt_duration(sec: int) -> str:
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    return f"{m}m {s}s"


def _pct(n: int, d: int) -> str:
    if d == 0:
        return "0%"
    return f"{(n / d) * 100:.0f}%"


def render_report(s: dict) -> str:
    out: list[str] = []
    total = s["total"]
    if total == 0:
        return "Corpus is empty (no files under output/by-channel/)."

    out.append("=== Overall ===")
    out.append(f"Total videos: {total}")
    out.append(f"Channels: {len(s['by_channel'])}")
    if s["publish_dates"]:
        out.append(f"Publish-date range: {min(s['publish_dates']).isoformat()} → {max(s['publish_dates']).isoformat()}")
    out.append(f"Total transcript duration: {_fmt_duration(s['total_duration_sec'])}")
    out.append(f"Enriched: {s['enriched_count']}/{total} ({_pct(s['enriched_count'], total)})")
    out.append("")

    out.append("=== By channel ===")
    rows = sorted(s["by_channel"].items(), key=lambda kv: -len(kv[1]))
    for slug, files in rows:
        enriched = sum(1 for f in files if f.get("enriched"))
        whisper = sum(1 for f in files if f.get("transcript_source") == "whisper")
        publish_dates = sorted(d for d in (_date(f.get("publish_date")) for f in files) if d)
        date_range = f"{publish_dates[0].isoformat()}..{publish_dates[-1].isoformat()}" if publish_dates else "(no dates)"
        out.append(f"  {slug:<24} videos={len(files):<4} enriched={enriched}/{len(files)} ({_pct(enriched, len(files))})  whisper={whisper}  range={date_range}")
    out.append("")

    out.append("=== Transcript source ===")
    for src, n in s["by_source"].most_common():
        out.append(f"  {src:<20} {n}  ({_pct(n, total)})")
    out.append("")

    if s["enriched_count"]:
        out.append("=== Content type (enriched only) ===")
        for ct, n in s["by_content_type"].most_common():
            out.append(f"  {ct:<20} {n}")
        out.append("")
        out.append("=== Audience level (enriched only) ===")
        for al, n in s["by_audience"].most_common():
            out.append(f"  {al:<20} {n}")
        out.append("")

    if s["flags_counter"]:
        out.append("=== Flags ===")
        for fl, n in s["flags_counter"].most_common():
            out.append(f"  {fl:<28} {n}")
        out.append("")

    if s["proposed_topics_counter"]:
        out.append("=== Proposed topics (cross-corpus; promote to taxonomy when frequent) ===")
        for term, n in s["proposed_topics_counter"].most_common(20):
            out.append(f"  {term:<32} {n}")
        out.append("")

    if s["recent_records"]:
        out.append("=== Recently ingested (last 7 days) ===")
        for ingest_date, vid, slug, title in sorted(s["recent_records"], reverse=True)[:10]:
            out.append(f"  {ingest_date} [{slug}] {vid} — {title}")
        out.append("")

    if s["parse_failures"]:
        out.append("=== Parse failures ===")
        for pf in s["parse_failures"]:
            out.append(f"  {pf}")
        out.append("")

    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Corpus status report.")
    parser.add_argument("--json", action="store_true", help="machine-readable JSON output")
    args = parser.parse_args()

    s = collect_stats()
    if args.json:
        # Make dates JSON-serializable
        out = {
            "total": s["total"],
            "channels": list(s["by_channel"].keys()),
            "by_channel_count": {k: len(v) for k, v in s["by_channel"].items()},
            "enriched_count": s["enriched_count"],
            "total_duration_sec": s["total_duration_sec"],
            "by_source": dict(s["by_source"]),
            "by_content_type": dict(s["by_content_type"]),
            "by_audience": dict(s["by_audience"]),
            "flags": dict(s["flags_counter"]),
            "proposed_topics_top20": dict(s["proposed_topics_counter"].most_common(20)),
            "parse_failures": s["parse_failures"],
        }
        print(json.dumps(out, indent=2, default=str))
    else:
        print(render_report(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
