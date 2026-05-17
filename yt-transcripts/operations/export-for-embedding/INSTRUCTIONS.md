# Skill: export-for-embedding

**Purpose**: Convert the enriched corpus into chunks ready for vector embedding. This is Layer 3 prep — it doesn't embed anything itself (no API calls, no provider commitments), but it produces the file format that a future embedding pipeline can consume directly.

**Input**: Optional `--dry-run` (default), `--output {path}` (default: `output/chunks.jsonl`).

**Output**: One JSONL file with one chunk per row, each carrying inherited file metadata. Or, in dry-run mode, just a report on what would be produced.

---

## How to run

Mechanical work in `scripts/export_chunks.py`. The skill invokes it.

**Dry-run first.** Before committing to a chunk strategy, run `--dry-run` to see chunk count, average chunk size, distribution. Adjust parameters in this doc if needed before doing a real export.

---

## Chunk strategy

For each `.md` file in `/output/by-channel/`:

1. **Parse the transcript body** — split on `[HH:MM:SS]` markers. Each marker starts a new "raw chunk."
2. **Coalesce** raw chunks into target-sized chunks of ~400 tokens (≈ 1600 chars for English text). Append raw chunks together until the next one would exceed the target; then close the chunk and start a new one.
3. **Overlap**: include the last ~50 tokens of the previous chunk at the start of the next chunk. This keeps semantic continuity for retrieval.
4. **Boundary preference**: never break mid-sentence. If a coalesced chunk ends mid-sentence, extend to the next sentence boundary (or the next `[HH:MM:SS]` marker) even if it overshoots the target slightly.
5. **Skip the description section** — the transcript body is the retrieval surface; description metadata goes in the chunk's inherited fields, not as a chunk itself.

Each chunk emits one JSONL row:

```json
{
  "chunk_id": "dQw4w9WgXcQ_c01",
  "video_id": "dQw4w9WgXcQ",
  "channel_slug": "competitor-a",
  "channel_name": "Competitor A",
  "title": "Video title",
  "publish_date": "2024-03-15",
  "url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
  "timestamp_start": "00:04:00",
  "timestamp_end": "00:06:30",
  "timestamp_url": "https://youtube.com/watch?v=dQw4w9WgXcQ&t=240s",
  "text": "Full chunk text, with timestamps stripped from the start of each cue but kept inline if Whisper inserted any mid-chunk.",
  "text_with_timestamps": "[00:04:00] Cue 1 text. [00:04:30] Cue 2 text. …",
  "char_count": 1623,
  "estimated_tokens": 405,

  "summary": "From enrichment — useful as document-level context for hybrid retrieval.",
  "topics": ["retirement-planning", "tax-strategy"],
  "entities_tickers": ["VTI", "VOO"],
  "entities_companies": ["Vanguard"],
  "content_type": "educational",
  "audience_level": "intermediate",
  "transcript_source": "manual_captions",
  "language": "en",

  "enriched": true,
  "ingest_version": 1,
  "enrichment_version": 1,
  "flags": []
}
```

`chunk_id` format: `{video_id}_c{NN}` (zero-padded, starting at `c01`). Stable across runs given the same chunk strategy.

`timestamp_url` uses YouTube's `&t={seconds}s` parameter so a retrieval result links directly to the moment in the video.

---

## What's included vs excluded

**Include in chunks:**
- Files with `enriched: true` (enrichment fields fill in valuable metadata).
- Files with `enriched: false` only if `--include-unenriched` flag is passed (metadata will be sparse).

**Exclude:**
- Files with `flags: [enrichment_failed]`.
- Files with `transcript_source: none` (no transcript to chunk).
- Files where `transcript_has_timestamps: false` (chunking depends on timestamp markers — would degrade to whole-file chunks).

Report skipped files and reasons in the run summary.

---

## What NOT to do

- Don't embed anything. This skill does not call an LLM or embedding provider — those decisions belong to Layer 3, which isn't built yet.
- Don't write chunks into `/output/by-channel/` — output goes to `output/chunks.jsonl` (or wherever `--output` points).
- Don't modify any source `.md` file.
- Don't commit `chunks.jsonl` to the repo (it's derived state and large — add to `.gitignore` if needed).

---

## When to run

- Dry-run early in the project to validate the chunk strategy against the actual corpus shape.
- Real export when Layer 3 starts, or whenever a retrieval pipeline needs fresh chunks.
- Re-run after any significant ingestion or re-enrichment batch.
