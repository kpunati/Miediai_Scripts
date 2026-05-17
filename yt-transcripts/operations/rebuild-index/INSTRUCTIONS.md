# Skill: rebuild-index

**Purpose**: Regenerate `output/index.csv` by walking every `.md` file under `/output/by-channel/` and extracting selected frontmatter fields into a single queryable CSV.

**Input**: None (operates on the full `/output/by-channel/` tree).

**Output**: `output/index.csv`, overwritten. One row per video.

---

## How to run

Just invoke. No arguments. Idempotent — running it twice produces identical output.

The mechanical work is done by `scripts/build_index.py`. The skill's role is to invoke the script and report results.

---

## Columns (in order)

| Column | Source |
|---|---|
| `video_id` | frontmatter |
| `channel_slug` | frontmatter |
| `channel_name` | frontmatter |
| `title` | frontmatter |
| `publish_date` | frontmatter |
| `duration_seconds` | frontmatter |
| `view_count_at_ingest` | frontmatter |
| `language` | frontmatter |
| `transcript_source` | frontmatter |
| `ingest_date` | frontmatter |
| `enriched` | frontmatter |
| `enrichment_date` | frontmatter |
| `content_type` | frontmatter (empty string if not enriched) |
| `audience_level` | frontmatter (empty string if not enriched) |
| `topics` | frontmatter, semicolon-joined (e.g. `"retirement;tax-strategy"`) |
| `topics_proposed` | frontmatter, semicolon-joined |
| `summary` | frontmatter (empty string if not enriched) |
| `flags` | frontmatter, semicolon-joined |
| `url` | frontmatter |
| `relpath` | derived: path relative to repo root, e.g. `output/by-channel/foo/2024-03-15_dQw4w9WgXcQ.md` |

CSV is RFC 4180 — quote any field containing commas, newlines, or quotes.

---

## What NOT to do

- Don't index files that fail schema validation (run `validate` first to catch them).
- Don't write any other file than `output/index.csv`.
- Don't include enrichment fields beyond what's listed above (entities and key_claims live in the files, not the index — keeps CSV tractable).

---

## When to run

- After every batch ingestion.
- After every enrichment batch.
- Whenever someone edits a `.md` file manually (rare but possible — notes field, manual flag, etc.).
- Before generating any report or sharing the catalog externally.

The output is derived state — if the CSV is missing or stale, just re-run; never edit it by hand.
