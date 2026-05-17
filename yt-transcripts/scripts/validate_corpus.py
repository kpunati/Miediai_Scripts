"""validate_corpus.py — schema/path/uniqueness/timestamp checks across /output.

Implements the canonical checks in operations/validate/INSTRUCTIONS.md against
the schema in schemas/frontmatter.schema.md. Read-only.

Usage:
  python scripts/validate_corpus.py              # report to stdout, exit non-zero on errors
  python scripts/validate_corpus.py --json       # machine-readable output
  python scripts/validate_corpus.py --channel <slug>  # restrict to one channel
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import frontmatter

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output" / "by-channel"
TAXONOMY_PATH = REPO_ROOT / "config" / "taxonomy.md"

REQUIRED_FIELDS = {
    "video_id": str,
    "url": str,
    "title": str,
    "channel_name": str,
    "channel_id": str,
    "channel_slug": str,
    "publish_date": (dt.date, str),
    "duration_seconds": int,
    "duration_human": str,
    "view_count_at_ingest": int,
    "language": str,
    "description": str,
    "tags_youtube": list,
    "transcript_source": str,
    "transcript_has_timestamps": bool,
    "ingest_date": (dt.date, str),
    "ingest_version": int,
    "enriched": bool,
    "enrichment_date": (dt.date, str, type(None)),
    "enrichment_version": (int, type(None)),
    "summary": str,
    "topics": list,
    "topics_proposed": list,
    "entities": dict,
    "content_type": str,
    "audience_level": str,
    "key_claims": list,
    "tags_topic": list,
    "usage_policy": str,
    "flags": list,
    "notes": str,
}

ENTITIES_REQUIRED_KEYS = {"people", "companies", "tickers", "funds", "products", "concepts"}

ALLOWED_TRANSCRIPT_SOURCE = {"manual_captions", "auto_captions", "whisper", "none"}
ALLOWED_CONTENT_TYPE = {"", "educational", "opinion", "news", "interview", "analysis", "case-study", "other"}
ALLOWED_AUDIENCE_LEVEL = {"", "beginner", "intermediate", "advanced", "mixed"}

FILENAME_RE = re.compile(r"^([a-z0-9][a-z0-9-]*)_(\d{4}-\d{2}-\d{2})_([A-Za-z0-9_-]{11})\.md$")
TIMESTAMP_MARKER_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]", re.MULTILINE)


class Finding:
    __slots__ = ("severity", "path", "message")

    def __init__(self, severity: str, path: Path, message: str):
        self.severity = severity
        self.path = path
        self.message = message

    def __repr__(self) -> str:
        return f"{self.severity}: {self.path} — {self.message}"


def _type_name(t: Any) -> str:
    if isinstance(t, tuple):
        return " | ".join(_type_name(x) for x in t)
    return getattr(t, "__name__", str(t))


def _isinstance_loose(value: Any, expected: Any) -> bool:
    # bool is a subclass of int in Python; we want them distinct here.
    if expected is int and isinstance(value, bool):
        return False
    if expected is bool and isinstance(value, bool):
        return True
    return isinstance(value, expected)


def _check_type(value: Any, expected: Any) -> bool:
    if isinstance(expected, tuple):
        return any(_isinstance_loose(value, e) for e in expected)
    return _isinstance_loose(value, expected)


def load_taxonomy_terms() -> set[str]:
    """Extract bare hyphenated terms from config/taxonomy.md (loose — terms appear in code spans or list items)."""
    if not TAXONOMY_PATH.exists():
        return set()
    text = TAXONOMY_PATH.read_text()
    terms: set[str] = set()
    # Grab single-quoted/backticked tokens that look like our lowercase-hyphenated form
    for match in re.finditer(r"`([a-z0-9][a-z0-9-]*)`", text):
        terms.add(match.group(1))
    # Also pick up bullet-list items like "- term-name"
    for match in re.finditer(r"^- ([a-z0-9][a-z0-9-]*)\s*$", text, flags=re.MULTILINE):
        terms.add(match.group(1))
    return terms


def validate_file(path: Path, video_id_seen: dict[str, Path], taxonomy: set[str]) -> list[Finding]:
    findings: list[Finding] = []

    # Parse frontmatter
    try:
        post = frontmatter.load(path)
    except Exception as e:
        findings.append(Finding("ERROR", path, f"frontmatter parse failed: {e}"))
        return findings

    fm = post.metadata
    body = post.content

    # 1. Required fields + types
    for field, expected in REQUIRED_FIELDS.items():
        if field not in fm:
            findings.append(Finding("ERROR", path, f"missing required field: {field}"))
            continue
        if not _check_type(fm[field], expected):
            findings.append(
                Finding(
                    "ERROR",
                    path,
                    f"field '{field}' has type {type(fm[field]).__name__}, expected {_type_name(expected)}",
                )
            )

    # 2. transcript_source enum
    if fm.get("transcript_source") not in ALLOWED_TRANSCRIPT_SOURCE:
        findings.append(
            Finding("ERROR", path, f"transcript_source '{fm.get('transcript_source')}' not in allowed enum")
        )

    # 3. content_type / audience_level enums
    if fm.get("content_type") not in ALLOWED_CONTENT_TYPE:
        findings.append(
            Finding("ERROR", path, f"content_type '{fm.get('content_type')}' not in allowed enum")
        )
    if fm.get("audience_level") not in ALLOWED_AUDIENCE_LEVEL:
        findings.append(
            Finding("ERROR", path, f"audience_level '{fm.get('audience_level')}' not in allowed enum")
        )

    # 4. video_id uniqueness
    vid = fm.get("video_id")
    if vid:
        prev = video_id_seen.get(vid)
        if prev:
            findings.append(Finding("ERROR", path, f"duplicate video_id '{vid}' (also in {prev.relative_to(REPO_ROOT)})"))
        else:
            video_id_seen[vid] = path

    # 5. Filename convention
    m = FILENAME_RE.match(path.name)
    if not m:
        findings.append(
            Finding(
                "ERROR",
                path,
                f"filename '{path.name}' does not match {{channel_slug}}_YYYY-MM-DD_{{video_id}}.md",
            )
        )
    else:
        slug_in_name, date_in_name, vid_in_name = m.groups()
        # 6. Filename date matches publish_date
        publish = fm.get("publish_date")
        publish_str = publish.isoformat() if isinstance(publish, dt.date) else str(publish)
        if date_in_name != publish_str:
            findings.append(
                Finding(
                    "ERROR",
                    path,
                    f"filename date '{date_in_name}' does not match publish_date '{publish_str}'",
                )
            )
        # 7. Filename video_id matches
        if vid_in_name != vid:
            findings.append(
                Finding("ERROR", path, f"filename video_id '{vid_in_name}' does not match frontmatter video_id '{vid}'")
            )
        # 8. Folder slug matches
        folder_slug = path.parent.name
        if folder_slug != slug_in_name:
            findings.append(
                Finding(
                    "ERROR",
                    path,
                    f"filename slug '{slug_in_name}' does not match folder '{folder_slug}'",
                )
            )
        if folder_slug != fm.get("channel_slug"):
            findings.append(
                Finding(
                    "ERROR",
                    path,
                    f"folder slug '{folder_slug}' does not match frontmatter channel_slug '{fm.get('channel_slug')}'",
                )
            )

    # 9. entities required keys
    entities = fm.get("entities", {})
    if isinstance(entities, dict):
        missing = ENTITIES_REQUIRED_KEYS - set(entities.keys())
        if missing:
            findings.append(Finding("ERROR", path, f"entities missing keys: {sorted(missing)}"))
        for k in ENTITIES_REQUIRED_KEYS & set(entities.keys()):
            if not isinstance(entities[k], list):
                findings.append(Finding("ERROR", path, f"entities.{k} is not a list"))

    # 10. transcript_has_timestamps true → at least one marker
    markers_in_body = TIMESTAMP_MARKER_RE.findall(body)
    if fm.get("transcript_has_timestamps") is True and not markers_in_body:
        findings.append(Finding("ERROR", path, "transcript_has_timestamps=true but no [HH:MM:SS] markers found in body"))

    # 11. If enriched, required fields are populated
    if fm.get("enriched") is True:
        if not fm.get("enrichment_date"):
            findings.append(Finding("ERROR", path, "enriched=true but enrichment_date is null/empty"))
        if not fm.get("enrichment_version"):
            findings.append(Finding("ERROR", path, "enriched=true but enrichment_version is null"))
        if not fm.get("summary") or not str(fm["summary"]).strip():
            findings.append(Finding("ERROR", path, "enriched=true but summary is empty"))
        elif not (50 <= len(fm["summary"]) <= 500):
            findings.append(
                Finding("ERROR", path, f"summary length {len(fm['summary'])} chars, must be 50–500")
            )
        # topics + topics_proposed ≤ 8
        n_topics = len(fm.get("topics") or []) + len(fm.get("topics_proposed") or [])
        if n_topics > 8:
            findings.append(Finding("ERROR", path, f"topics + topics_proposed = {n_topics}, must be ≤ 8"))
        # Required body sections
        for section in ("## Summary", "## Key Takeaways", "## Detailed Notes"):
            if section + "\n" not in body and not body.lstrip().startswith(section):
                # Check more leniently for trailing whitespace variations
                if not re.search(rf"^{re.escape(section)}\s*$", body, flags=re.MULTILINE):
                    findings.append(Finding("ERROR", path, f"enriched=true but body is missing section '{section}'"))
        # Detailed Notes must have at least one ### subsection
        notes_match = re.search(r"## Detailed Notes\s*\n(.*?)(?=\n## |\Z)", body, flags=re.DOTALL)
        if notes_match:
            sub_pattern = re.compile(r"^### .*\[(\d{2}:\d{2}:\d{2})\]\s*$", flags=re.MULTILINE)
            subs = sub_pattern.findall(notes_match.group(1))
            if not subs:
                findings.append(Finding("ERROR", path, "Detailed Notes has no '### Subheading [HH:MM:SS]' subsections"))
            else:
                for ts in subs:
                    if ts not in set(markers_in_body):
                        findings.append(Finding("ERROR", path, f"Detailed Notes subheading timestamp '{ts}' not in transcript markers"))

    # 12. tags_topic mirrors topics
    if fm.get("tags_topic") != fm.get("topics"):
        findings.append(Finding("ERROR", path, "tags_topic must mirror topics (legacy alias)"))

    # 13. topics_proposed has no overlap with topics
    overlap = set(fm.get("topics") or []) & set(fm.get("topics_proposed") or [])
    if overlap:
        findings.append(Finding("ERROR", path, f"topics_proposed overlaps with topics: {sorted(overlap)}"))

    # 14. key_claims timestamps must match body markers
    marker_set = set(markers_in_body)
    for i, kc in enumerate(fm.get("key_claims") or []):
        if not isinstance(kc, dict):
            findings.append(Finding("ERROR", path, f"key_claims[{i}] is not a dict"))
            continue
        ts = kc.get("timestamp")
        if not ts:
            findings.append(Finding("ERROR", path, f"key_claims[{i}] missing timestamp"))
            continue
        if ts not in marker_set:
            findings.append(
                Finding(
                    "ERROR",
                    path,
                    f"key_claims[{i}] timestamp '{ts}' not present in transcript body markers",
                )
            )
        if kc.get("confidence") not in {"high", "medium", "low"}:
            findings.append(
                Finding("ERROR", path, f"key_claims[{i}] confidence '{kc.get('confidence')}' invalid")
            )
        if not isinstance(kc.get("flagged"), bool):
            findings.append(Finding("ERROR", path, f"key_claims[{i}] flagged must be bool"))

    # 15. controlled-vocab check on topics (warning if taxonomy empty)
    if fm.get("topics"):
        if not taxonomy:
            for t in fm["topics"]:
                findings.append(Finding("WARN", path, f"topic '{t}' but taxonomy.md is empty — treat as proposed"))
        else:
            for t in fm["topics"]:
                if t not in taxonomy:
                    findings.append(Finding("WARN", path, f"topic '{t}' not in controlled vocab (config/taxonomy.md)"))

    return findings


def main() -> int:
    p = argparse.ArgumentParser(description="Validate the yt-transcripts corpus against the schema.")
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    p.add_argument("--channel", help="restrict to a single channel slug")
    args = p.parse_args()

    if not OUTPUT_DIR.exists():
        print(f"No output/by-channel directory found at {OUTPUT_DIR}")
        return 0

    target_root = OUTPUT_DIR / args.channel if args.channel else OUTPUT_DIR
    if args.channel and not target_root.exists():
        print(f"Channel folder not found: {target_root}")
        return 2

    files = sorted(target_root.rglob("*.md"))
    if not files:
        print(f"No .md files found under {target_root}")
        return 0

    taxonomy = load_taxonomy_terms()
    seen_ids: dict[str, Path] = {}
    all_findings: list[Finding] = []
    for fp in files:
        all_findings.extend(validate_file(fp, seen_ids, taxonomy))

    errors = [f for f in all_findings if f.severity == "ERROR"]
    warns = [f for f in all_findings if f.severity == "WARN"]

    if args.json:
        result = {
            "total_files": len(files),
            "errors": [{"path": str(f.path.relative_to(REPO_ROOT)), "message": f.message} for f in errors],
            "warnings": [{"path": str(f.path.relative_to(REPO_ROOT)), "message": f.message} for f in warns],
            "ok": not errors,
        }
        print(json.dumps(result, indent=2))
        return 0 if not errors else 1

    # Human-readable report
    by_file_err: dict[Path, list[str]] = defaultdict(list)
    by_file_warn: dict[Path, list[str]] = defaultdict(list)
    for f in errors:
        by_file_err[f.path].append(f.message)
    for f in warns:
        by_file_warn[f.path].append(f.message)

    if errors:
        print("== ERRORS (must fix) ==")
        for fp, msgs in by_file_err.items():
            print(f"\n  {fp.relative_to(REPO_ROOT)}")
            for m in msgs:
                print(f"    - {m}")
        print()

    if warns:
        print("== WARNINGS (consider fixing) ==")
        for fp, msgs in by_file_warn.items():
            print(f"\n  {fp.relative_to(REPO_ROOT)}")
            for m in msgs:
                print(f"    - {m}")
        print()

    print("== STATS ==")
    err_files = len(by_file_err)
    print(f"Total files: {len(files)}")
    print(f"Errors: {len(errors)} (in {err_files} file{'s' if err_files != 1 else ''})")
    print(f"Warnings: {len(warns)}")
    print(f"Validation result: {'PASS' if not errors else 'FAIL'}")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
