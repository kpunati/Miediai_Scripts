"""list_whisper.py — rank files needing human spot-check of extracted facts.

Per the user decision: this skill covers ANY file with the `whisper_review_needed`
flag, regardless of transcript_source. The flag is set by enrichment whenever
specific numbers/tickers/dollar amounts are extracted from a low-trust source
(auto_captions or whisper). The actual Whisper backlog is zero today; the
auto-caption backlog is large, and it's the same human task either way.

See operations/review-whisper/INSTRUCTIONS.md for the canonical spec.

Usage:
  python scripts/list_whisper.py                          # top 10 by view count
  python scripts/list_whisper.py --limit 25
  python scripts/list_whisper.py --channel ishares
  python scripts/list_whisper.py --all                    # every flagged file
  python scripts/list_whisper.py --source whisper         # whisper-only (currently 0)
  python scripts/list_whisper.py --json                   # machine-readable
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import frontmatter

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output" / "by-channel"


def _is_reviewed(notes: str | None) -> bool:
    return "whisper_reviewed:" in (notes or "")


def _flagged_claims_count(fm: dict) -> int:
    return sum(1 for kc in (fm.get("key_claims") or []) if isinstance(kc, dict) and kc.get("flagged"))


def collect(channel: str | None, source_filter: str | None) -> list[dict]:
    if not OUTPUT_DIR.exists():
        return []
    root = OUTPUT_DIR / channel if channel else OUTPUT_DIR
    if channel and not root.exists():
        print(f"ERROR: channel folder not found: {root}", file=sys.stderr)
        sys.exit(2)

    rows: list[dict] = []
    for fp in sorted(root.rglob("*.md")):
        try:
            fm = frontmatter.load(fp).metadata
        except Exception:
            continue
        flags = fm.get("flags") or []
        if "whisper_review_needed" not in flags:
            continue
        if source_filter and fm.get("transcript_source") != source_filter:
            continue
        if _is_reviewed(fm.get("notes")):
            continue
        rows.append({
            "path": str(fp.relative_to(REPO_ROOT)),
            "video_id": fm.get("video_id"),
            "channel_slug": fm.get("channel_slug"),
            "title": fm.get("title"),
            "publish_date": str(fm.get("publish_date")),
            "transcript_source": fm.get("transcript_source"),
            "view_count_at_ingest": fm.get("view_count_at_ingest") or 0,
            "duration_human": fm.get("duration_human"),
            "url": fm.get("url"),
            "flagged_claims": _flagged_claims_count(fm),
            "tickers": fm.get("entities", {}).get("tickers") or [],
        })
    rows.sort(key=lambda r: r["view_count_at_ingest"], reverse=True)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--all", action="store_true", help="ignore --limit")
    ap.add_argument("--channel", help="restrict to one channel_slug")
    ap.add_argument("--source", choices=["whisper", "auto_captions", "manual_captions"], help="filter by transcript_source")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--csv", action="store_true", help="write CSV to stdout")
    args = ap.parse_args()

    rows = collect(args.channel, args.source)
    total = len(rows)
    if not args.all:
        rows = rows[: args.limit]

    if args.json:
        print(json.dumps({"total_matching": total, "shown": len(rows), "rows": rows}, indent=2, default=str))
        return 0

    if args.csv:
        w = csv.DictWriter(sys.stdout, fieldnames=["video_id", "channel_slug", "publish_date", "view_count_at_ingest", "flagged_claims", "transcript_source", "title", "url", "path"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in w.fieldnames})
        return 0

    if not rows:
        scope = f" (channel={args.channel})" if args.channel else ""
        print(f"No unreviewed files with whisper_review_needed flag{scope}.")
        return 0

    print(f"{total} unreviewed file(s) with whisper_review_needed; showing {len(rows)}.\n")
    print(f"{'views':>10}  {'flagged':>7}  {'date':<10}  {'src':<14}  title")
    print("-" * 110)
    for r in rows:
        title = (r["title"] or "")[:55]
        print(f"{r['view_count_at_ingest']:>10}  {r['flagged_claims']:>7}  {r['publish_date']:<10}  {(r['transcript_source'] or ''):<14}  {title}")
        print(f"{'':>10}  {r['url']}")
    print()
    print(f"Next: open the top file, verify its `key_claims` (flagged ones first) and `entities.tickers`/`entities.funds` against the transcript.")
    print(f"      When done, append `whisper_reviewed: YYYY-MM-DD` to that file's `notes` (see operations/review-whisper/INSTRUCTIONS.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
