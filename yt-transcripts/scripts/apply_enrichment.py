"""apply_enrichment.py — write enrichment output into a transcript file safely.

This is the canonical applier. Every enrichment batch (human or agent) should
call it instead of writing ad-hoc regex-substitution scripts. It bakes in the
fixes we learned the hard way:

  - Auto-trim oversize summaries at the last sentence boundary before 470 chars.
  - Snap every key_claims[].timestamp and Detailed-Notes subsection timestamp to
    the nearest *preceding* [HH:MM:SS] marker actually present in the transcript
    body (this is the #1 hallucination from LLMs).
  - Dedupe + lowercase topics; cap topics + topics_proposed at 8.
  - Mirror tags_topic to topics.
  - Ensure entities has all six required keys, each a list.
  - Emit YAML with no `key_claims:[]` (missing-space) bug — lists are always
    rendered with a space after the colon.

Input: a JSON payload (path or stdin) of this shape:

  {
    "file": "output/by-channel/.../slug_YYYY-MM-DD_VIDEOID.md",
    "summary": "1-3 sentences, neutral & factual.",
    "topics": ["controlled-term-a"],
    "topics_proposed": ["new-term-b"],
    "entities": {
      "people":    [{"name": "Jane", "role": "CFP"}],
      "companies": [{"name": "Acme", "ticker": null}],
      "tickers":   ["VTI"],
      "funds":     [{"name": "Vanguard Total Stock", "ticker": "VTI"}],
      "products":  ["M1 Finance"],
      "concepts":  ["dollar-cost-averaging"]
    },
    "content_type": "educational",
    "audience_level": "intermediate",
    "key_claims": [
      {"claim": "...", "timestamp": "00:04:12", "confidence": "medium", "flagged": false}
    ],
    "flags_to_add": ["whisper_review_needed"],   # appended, never replaces
    "body": {
      "summary": "2-4 sentence readable summary.",
      "key_takeaways": ["bullet 1", "bullet 2", "bullet 3", "bullet 4"],
      "detailed_notes": [
        {"heading": "...", "timestamp": "00:00:04", "notes": "..."},
        ...
      ]
    }
  }

CLI:
  python scripts/apply_enrichment.py --json payload.json
  cat payload.json | python scripts/apply_enrichment.py --stdin
  python scripts/apply_enrichment.py --json payload.json --dry-run

Exit codes:
  0  applied (or dry-run preview OK)
  1  validation failed (no write attempted)
  2  bad input (file missing, JSON invalid, etc.)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SUMMARY_HARD_MAX = 500
SUMMARY_TRIM_TARGET = 470  # snap at last sentence ending before this
SUMMARY_MIN = 50
TOPICS_COMBINED_MAX = 8

ENTITIES_KEYS = ["people", "companies", "tickers", "funds", "products", "concepts"]

ALLOWED_CONTENT_TYPE = {"educational", "opinion", "news", "interview", "analysis", "case-study", "other"}
ALLOWED_AUDIENCE_LEVEL = {"beginner", "intermediate", "advanced", "mixed"}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}

TIMESTAMP_MARKER_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]", re.MULTILINE)
TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")


# ---------- helpers ----------------------------------------------------------

def _ts_to_seconds(ts: str) -> int:
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def snap_to_preceding_marker(ts: str, markers: list[str]) -> str:
    """Return the latest marker <= ts. If ts is before all markers, return the first."""
    if not markers:
        raise ValueError("transcript has no [HH:MM:SS] markers — cannot snap")
    if not TIMESTAMP_RE.match(ts):
        # If malformed entirely, fall back to first marker.
        return markers[0]
    target = _ts_to_seconds(ts)
    chosen = markers[0]
    for m in markers:
        if _ts_to_seconds(m) <= target:
            chosen = m
        else:
            break
    return chosen


def trim_summary(s: str) -> str:
    """If summary > SUMMARY_HARD_MAX, trim at the last sentence-ending punctuation
    before SUMMARY_TRIM_TARGET. Falls back to a hard cut + ellipsis if no boundary."""
    if len(s) <= SUMMARY_HARD_MAX:
        return s
    head = s[:SUMMARY_TRIM_TARGET]
    # Find last sentence boundary (., !, ?) followed by a space or end.
    boundaries = [i for i, ch in enumerate(head) if ch in ".!?"]
    if boundaries:
        cut = boundaries[-1] + 1
        return head[:cut].rstrip()
    return head.rstrip() + "..."


def yq(s: str) -> str:
    """Render a string as a double-quoted YAML scalar with proper escapes."""
    return json.dumps(s, ensure_ascii=False)


def ylist_inline(items: list[str]) -> str:
    """Render a list of strings as inline JSON-style YAML (always a space after `:`)."""
    if not items:
        return "[]"
    return "[" + ", ".join(yq(x) for x in items) + "]"


def render_entities(entities: dict) -> str:
    """Render the entities object as a YAML block — matches the corpus style."""
    lines = []
    # people
    people = entities.get("people") or []
    if people:
        lines.append("  people:")
        for p in people:
            lines.append(f"    - name: {yq(p['name'])}")
            if p.get("role"):
                lines.append(f"      role: {yq(p['role'])}")
    else:
        lines.append("  people: []")
    # companies
    companies = entities.get("companies") or []
    if companies:
        lines.append("  companies:")
        for c in companies:
            lines.append(f"    - name: {yq(c['name'])}")
            ticker = c.get("ticker")
            lines.append(f"      ticker: {yq(ticker) if ticker else 'null'}")
    else:
        lines.append("  companies: []")
    # tickers
    lines.append(f"  tickers: {ylist_inline(entities.get('tickers') or [])}")
    # funds
    funds = entities.get("funds") or []
    if funds:
        lines.append("  funds:")
        for f in funds:
            lines.append(f"    - name: {yq(f['name'])}")
            ticker = f.get("ticker")
            lines.append(f"      ticker: {yq(ticker) if ticker else 'null'}")
    else:
        lines.append("  funds: []")
    # products
    lines.append(f"  products: {ylist_inline(entities.get('products') or [])}")
    # concepts
    lines.append(f"  concepts: {ylist_inline(entities.get('concepts') or [])}")
    return "\n".join(lines)


def render_key_claims(kc_list: list[dict]) -> str:
    if not kc_list:
        return "[]"
    parts = [""]  # leading newline so the block starts on its own line
    for kc in kc_list:
        parts.append(f"  - claim: {yq(kc['claim'])}")
        parts.append(f"    timestamp: {yq(kc['timestamp'])}")
        parts.append(f"    confidence: {yq(kc['confidence'])}")
        parts.append(f"    flagged: {'true' if kc['flagged'] else 'false'}")
    return "\n".join(parts)


# ---------- core -------------------------------------------------------------

def normalize_payload(payload: dict, markers: list[str]) -> tuple[dict, list[str]]:
    """Apply auto-fixes and return (normalized_payload, notes_for_user)."""
    notes: list[str] = []

    # summary
    summary = (payload.get("summary") or "").strip()
    if not summary:
        raise ValueError("payload missing 'summary'")
    if len(summary) > SUMMARY_HARD_MAX:
        original_len = len(summary)
        summary = trim_summary(summary)
        notes.append(f"summary trimmed from {original_len} → {len(summary)} chars at sentence boundary")
    if len(summary) < SUMMARY_MIN:
        raise ValueError(f"summary length {len(summary)} < {SUMMARY_MIN}")
    payload["summary"] = summary

    # topics + topics_proposed
    topics = [t.strip().lower() for t in (payload.get("topics") or []) if t.strip()]
    topics_proposed = [t.strip().lower() for t in (payload.get("topics_proposed") or []) if t.strip()]
    # dedupe preserving order
    seen: set[str] = set()
    topics = [t for t in topics if not (t in seen or seen.add(t))]
    seen.clear()
    topics_proposed = [t for t in topics_proposed if not (t in seen or seen.add(t))]
    # remove overlap (controlled wins)
    topics_proposed = [t for t in topics_proposed if t not in set(topics)]
    # cap combined at 8 (drop from the tail of topics_proposed first)
    combined = len(topics) + len(topics_proposed)
    if combined > TOPICS_COMBINED_MAX:
        drop = combined - TOPICS_COMBINED_MAX
        kept = max(0, len(topics_proposed) - drop)
        dropped = topics_proposed[kept:]
        topics_proposed = topics_proposed[:kept]
        notes.append(f"dropped {len(dropped)} topics_proposed to fit ≤8 cap: {dropped}")
    payload["topics"] = topics
    payload["topics_proposed"] = topics_proposed

    # entities
    entities = payload.get("entities") or {}
    for k in ENTITIES_KEYS:
        if k not in entities or entities[k] is None:
            entities[k] = []
        if not isinstance(entities[k], list):
            raise ValueError(f"entities.{k} must be a list")
    payload["entities"] = entities

    # enums
    ct = payload.get("content_type", "")
    if ct not in ALLOWED_CONTENT_TYPE:
        raise ValueError(f"content_type {ct!r} not in {sorted(ALLOWED_CONTENT_TYPE)}")
    al = payload.get("audience_level", "")
    if al not in ALLOWED_AUDIENCE_LEVEL:
        raise ValueError(f"audience_level {al!r} not in {sorted(ALLOWED_AUDIENCE_LEVEL)}")

    # key_claims: snap timestamps, validate fields
    fixed_kc = []
    for i, kc in enumerate(payload.get("key_claims") or []):
        for field in ("claim", "timestamp", "confidence"):
            if field not in kc:
                raise ValueError(f"key_claims[{i}] missing {field}")
        if "flagged" not in kc:
            kc["flagged"] = False
        if kc["confidence"] not in ALLOWED_CONFIDENCE:
            raise ValueError(f"key_claims[{i}].confidence {kc['confidence']!r} invalid")
        original_ts = kc["timestamp"]
        snapped = snap_to_preceding_marker(original_ts, markers)
        if snapped != original_ts:
            notes.append(f"key_claims[{i}] timestamp {original_ts} → {snapped} (snapped to nearest preceding marker)")
        kc["timestamp"] = snapped
        fixed_kc.append(kc)
    payload["key_claims"] = fixed_kc

    # body — snap detailed_notes timestamps too
    body = payload.get("body") or {}
    notes_list = body.get("detailed_notes") or []
    if not notes_list:
        raise ValueError("body.detailed_notes must have at least 1 subsection")
    for i, sub in enumerate(notes_list):
        for field in ("heading", "timestamp", "notes"):
            if field not in sub:
                raise ValueError(f"body.detailed_notes[{i}] missing {field}")
        snapped = snap_to_preceding_marker(sub["timestamp"], markers)
        if snapped != sub["timestamp"]:
            notes.append(f"detailed_notes[{i}] timestamp {sub['timestamp']} → {snapped}")
        sub["timestamp"] = snapped
    if not body.get("summary"):
        raise ValueError("body.summary required")
    takeaways = body.get("key_takeaways") or []
    if len(takeaways) < 3:
        raise ValueError(f"body.key_takeaways must have ≥3 bullets, got {len(takeaways)}")
    payload["body"] = body

    return payload, notes


# ---------- file mutation ----------------------------------------------------

def _replace_frontmatter_field_block(fm_text: str, key: str, new_block: str) -> str:
    """Replace `key:` and its value block (until next top-level key or end of fm).
    `new_block` should be the literal replacement, starting with `key:`."""
    # match `key:` at start of a line, then everything up to the next top-level key or end.
    pattern = re.compile(
        rf"^{re.escape(key)}:.*?(?=^\S|^# ===|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    if not pattern.search(fm_text):
        raise ValueError(f"frontmatter field {key!r} not found — file may not be ingest-shaped")
    return pattern.sub(new_block.rstrip() + "\n", fm_text, count=1)


def render_body_sections(body: dict) -> str:
    out = ["## Summary", "", body["summary"].strip(), "", "## Key Takeaways", ""]
    for b in body["key_takeaways"]:
        out.append(f"- {b.strip()}")
    out.append("")
    out.append("## Detailed Notes")
    out.append("")
    for sub in body["detailed_notes"]:
        out.append(f"### {sub['heading'].strip()} [{sub['timestamp']}]")
        out.append("")
        out.append(sub["notes"].strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def apply_to_file(file_path: Path, payload: dict, dry_run: bool = False) -> list[str]:
    raw = file_path.read_text()

    fm_match = re.match(r"^---\n(.*?\n)---\n", raw, flags=re.DOTALL)
    if not fm_match:
        raise ValueError("file has no YAML frontmatter delimited by ---")
    fm_text = fm_match.group(1)
    body_text = raw[fm_match.end():]

    markers = TIMESTAMP_MARKER_RE.findall(body_text)
    if not markers:
        raise ValueError("transcript body has no [HH:MM:SS] markers")

    payload, notes = normalize_payload(payload, markers)

    # --- rewrite frontmatter fields one-by-one ---
    today = dt.date.today().isoformat()
    p = payload

    fm_text = _replace_frontmatter_field_block(fm_text, "enriched", "enriched: true")
    fm_text = _replace_frontmatter_field_block(fm_text, "enrichment_date", f"enrichment_date: {today}")
    fm_text = _replace_frontmatter_field_block(fm_text, "enrichment_version", "enrichment_version: 1")
    fm_text = _replace_frontmatter_field_block(fm_text, "summary", f"summary: {yq(p['summary'])}")
    fm_text = _replace_frontmatter_field_block(fm_text, "topics", f"topics: {ylist_inline(p['topics'])}")
    fm_text = _replace_frontmatter_field_block(fm_text, "topics_proposed", f"topics_proposed: {ylist_inline(p['topics_proposed'])}")
    fm_text = _replace_frontmatter_field_block(fm_text, "entities", f"entities:\n{render_entities(p['entities'])}")
    fm_text = _replace_frontmatter_field_block(fm_text, "content_type", f"content_type: {yq(p['content_type'])}")
    fm_text = _replace_frontmatter_field_block(fm_text, "audience_level", f"audience_level: {yq(p['audience_level'])}")
    fm_text = _replace_frontmatter_field_block(fm_text, "key_claims", f"key_claims: {render_key_claims(p['key_claims'])}")
    fm_text = _replace_frontmatter_field_block(fm_text, "tags_topic", f"tags_topic: {ylist_inline(p['topics'])}")

    # flags: read existing, append new ones (dedup), keep order stable.
    flags_block_re = re.compile(r"^flags:\s*\[(.*?)\]", re.MULTILINE)
    flags_match = flags_block_re.search(fm_text)
    if flags_match:
        existing_raw = flags_match.group(1).strip()
        existing = [x.strip().strip('"').strip("'") for x in existing_raw.split(",") if x.strip()] if existing_raw else []
    else:
        existing = []
    for f in payload.get("flags_to_add") or []:
        if f not in existing:
            existing.append(f)
    fm_text = _replace_frontmatter_field_block(fm_text, "flags", f"flags: {ylist_inline(existing)}")

    # --- rewrite body: insert/replace enrichment sections before ## Transcript ---
    transcript_idx = body_text.find("## Transcript")
    if transcript_idx == -1:
        raise ValueError("body has no `## Transcript` section")
    header_block = body_text[:transcript_idx].rstrip()
    # If enrichment sections were previously inserted, strip them — re-find the
    # last blank line before any `## Summary` so we keep the title/header block.
    header_block = re.split(r"\n## Summary\b", header_block, maxsplit=1)[0].rstrip()

    new_body_sections = render_body_sections(payload["body"])
    new_body = (
        header_block
        + "\n\n"
        + new_body_sections
        + "\n"
        + body_text[transcript_idx:]
    )

    new_raw = "---\n" + fm_text + "---\n" + new_body

    if dry_run:
        return notes + [f"[dry-run] would write {len(new_raw)} bytes to {file_path}"]
    file_path.write_text(new_raw)
    return notes + [f"wrote {file_path}"]


# ---------- CLI --------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Apply an enrichment payload to a transcript file.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--json", type=Path, help="path to a JSON payload")
    src.add_argument("--stdin", action="store_true", help="read JSON payload from stdin")
    ap.add_argument("--dry-run", action="store_true", help="validate and print, do not write")
    args = ap.parse_args()

    try:
        if args.stdin:
            payload = json.loads(sys.stdin.read())
        else:
            payload = json.loads(args.json.read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON payload: {e}", file=sys.stderr)
        return 2

    file_str = payload.get("file")
    if not file_str:
        print("ERROR: payload missing 'file' key", file=sys.stderr)
        return 2
    fp = Path(file_str)
    if not fp.is_absolute():
        fp = REPO_ROOT / fp
    if not fp.exists():
        print(f"ERROR: file not found: {fp}", file=sys.stderr)
        return 2

    try:
        notes = apply_to_file(fp, payload, dry_run=args.dry_run)
    except ValueError as e:
        print(f"VALIDATION ERROR: {e}", file=sys.stderr)
        return 1

    for n in notes:
        print(n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
