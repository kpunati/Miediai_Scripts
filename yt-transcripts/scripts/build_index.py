"""scripts/build_index.py — regenerate output/index.csv from frontmatter.

See operations/rebuild-index/INSTRUCTIONS.md for column list and semantics.

Usage:
  python scripts/build_index.py             # writes output/index.csv
  python scripts/build_index.py --check     # parse-only, no write, exit non-zero if any file fails to parse
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from pathlib import Path

import frontmatter

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output" / "by-channel"
INDEX_CSV = REPO_ROOT / "output" / "index.csv"

COLUMNS = [
    "video_id",
    "channel_slug",
    "channel_name",
    "title",
    "publish_date",
    "duration_seconds",
    "view_count_at_ingest",
    "language",
    "transcript_source",
    "ingest_date",
    "enriched",
    "enrichment_date",
    "content_type",
    "audience_level",
    "topics",
    "topics_proposed",
    "summary",
    "flags",
    "url",
    "relpath",
]


def _semicolon_join(value) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        return ";".join(str(v) for v in value)
    return str(value)


def _date_str(value) -> str:
    if isinstance(value, dt.date):
        return value.isoformat()
    return "" if value is None else str(value)


def row_from_file(path: Path) -> dict | None:
    try:
        post = frontmatter.load(path)
    except Exception as e:
        print(f"WARN: failed to parse {path.relative_to(REPO_ROOT)}: {e}", file=sys.stderr)
        return None
    fm = post.metadata
    return {
        "video_id": fm.get("video_id", ""),
        "channel_slug": fm.get("channel_slug", ""),
        "channel_name": fm.get("channel_name", ""),
        "title": fm.get("title", ""),
        "publish_date": _date_str(fm.get("publish_date")),
        "duration_seconds": fm.get("duration_seconds", ""),
        "view_count_at_ingest": fm.get("view_count_at_ingest", ""),
        "language": fm.get("language", ""),
        "transcript_source": fm.get("transcript_source", ""),
        "ingest_date": _date_str(fm.get("ingest_date")),
        "enriched": fm.get("enriched", False),
        "enrichment_date": _date_str(fm.get("enrichment_date")),
        "content_type": fm.get("content_type", ""),
        "audience_level": fm.get("audience_level", ""),
        "topics": _semicolon_join(fm.get("topics")),
        "topics_proposed": _semicolon_join(fm.get("topics_proposed")),
        "summary": fm.get("summary", ""),
        "flags": _semicolon_join(fm.get("flags")),
        "url": fm.get("url", ""),
        "relpath": str(path.relative_to(REPO_ROOT)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate output/index.csv from frontmatter.")
    parser.add_argument("--check", action="store_true", help="parse-only, don't write")
    args = parser.parse_args()

    if not OUTPUT_DIR.exists():
        print(f"No output/by-channel directory: {OUTPUT_DIR}")
        return 0

    files = sorted(OUTPUT_DIR.rglob("*.md"))
    rows = []
    fails = 0
    for fp in files:
        r = row_from_file(fp)
        if r is None:
            fails += 1
            continue
        rows.append(r)

    if args.check:
        print(f"Parsed {len(rows)} / {len(files)} files; {fails} failed")
        return 0 if fails == 0 else 1

    INDEX_CSV.parent.mkdir(parents=True, exist_ok=True)
    with INDEX_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {INDEX_CSV.relative_to(REPO_ROOT)} — {len(rows)} rows ({fails} files failed to parse)")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
