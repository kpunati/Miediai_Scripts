# Skill: status

**Purpose**: Quick "what's in the corpus" dashboard. Counts, percentages, breakdowns. For personal sanity and for management updates.

**Input**: None (reads `/output/by-channel/`).

**Output**: A formatted report to stdout.

---

## How to run

Just invoke. No arguments. Read-only.

Mechanical work in `scripts/corpus_status.py`. The skill invokes it and presents the report — optionally with a brief narrative summary if the user wants one.

---

## Report sections

### Overall

- Total videos in catalog
- Total channels
- Date range (oldest publish_date → newest)
- Total duration (sum of `duration_seconds`, formatted as hours)
- Total transcript word count (rough estimate)
- Disk usage of `/output`

### By channel

Table sorted by video count descending:

```
channel_slug              videos  earliest    latest      enriched  whisper%
competitor-a              42      2022-03-12  2025-11-02  38/42     5%
competitor-b              17      2024-01-05  2025-10-30  17/17     0%
…
```

### Enrichment status

- Total enriched: X / Y (Z%)
- Enrichment versions in use (e.g. v1: 120 files)
- Files where `enriched: false`: count

### Transcript source breakdown

- manual_captions: count (%)
- auto_captions: count (%)
- whisper: count (%)
- none: count (%) — these are videos where transcript pull failed

### Flags

- Count of files with any flag, broken down by flag name:
  - `whisper_review_needed`: 12
  - `enrichment_failed`: 1
  - `sensitive_content`: 0

### Content type distribution (enriched only)

Bar-chart-ish counts per `content_type`.

### Recently ingested (last 7 days)

List of the most recent N (default 10) files added — `ingest_date`, video_id, channel, title.

### Proposed topics (cross-corpus)

Aggregate every `topics_proposed` entry across all enriched files, count occurrences, sort descending. Show the top 20 (or all, if fewer).

This is the on-ramp for promoting terms to the controlled vocabulary in [`config/taxonomy.md`](../../config/taxonomy.md): when a term appears in `topics_proposed` across 5+ files, it's a strong candidate for promotion. Output format:

```
Proposed topic              files
etfs                        12
long-term-investing         9
retirement-planning         7
…
```

After promotion: a term moves from `topics_proposed` to a controlled section of `taxonomy.md`, and the next enrichment run (or `re-enrich`) will start placing it in `topics` instead of `topics_proposed`.

---

## What NOT to do

- Don't modify any file.
- Don't include enrichment fields if no files are enriched yet (show "0 enriched, run `enrich` skill to start").
- Don't fail loudly if `/output/by-channel/` is empty — just report "corpus is empty."

---

## When to run

- Whenever you want a snapshot.
- Before status updates to management.
- After big ingestion or enrichment batches.
