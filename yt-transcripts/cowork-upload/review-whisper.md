# Skill: review-whisper

**Purpose**: Surface files carrying the `whisper_review_needed` flag for human verification of extracted facts. The flag is set in two places:

- **By ingest**, when `transcript_source: whisper` (the captionless fallback transcribes via local Whisper, which is known weak on finance content).
- **By enrichment**, whenever specific numbers / tickers / fund names / dollar amounts were extracted from any low-trust source (`auto_captions` or `whisper`). The point is the same either way: humans should sanity-check the extracted facts against the video.

Scope is intentionally broad — the skill covers both cases, not just whisper-sourced files. As of writing, the actual whisper backlog is zero and the auto-captions backlog is the entire flagged set.

**Input**: Optional limit (default: 10 files), optional channel filter.

**Output**: A ranked list of files needing review, plus an interactive walkthrough if the user wants.

---

## How to run

Two modes:

**List mode** (default): show the top N Whisper-transcribed files sorted by `view_count_at_ingest` descending (review the most-watched first — they're the highest-stakes).

**Walkthrough mode**: for each file in the list, open it, show the key claims (post-enrichment) and any flagged segments, and ask the reviewer to confirm / flag / re-transcribe.

Mechanical part (the ranked list) is in `scripts/list_whisper.py`. The walkthrough is agent-driven.

---

## Selection logic

Filter to files where:
- `whisper_review_needed` in `flags` (set by ingest or by enrichment)
- AND `notes` does not contain `"whisper_reviewed:"` (lets reviewer mark files as reviewed without removing the flag)

Optional filters:
- `--channel {slug}` — restrict to one channel
- `--source {whisper|auto_captions|manual_captions}` — restrict by transcript source
- `--limit N` — number of files to surface (default 10)
- `--all` — show every matching file regardless of count

Sort: `view_count_at_ingest` descending.

---

## Walkthrough flow (per file)

For each file in the ranked list:

1. Display: title, channel, publish_date, duration, view_count, URL.
2. If enriched, show the extracted `key_claims` and `entities.tickers` / `entities.funds`.
3. Ask the reviewer:
   - **(a) Looks good** → append `whisper_reviewed: YYYY-MM-DD` to `notes`; optionally remove `whisper_review_needed` from `flags`.
   - **(b) Specific issues** → reviewer specifies which claim/entity is wrong; agent records them in `notes` (e.g. `whisper_review: ticker AAPL likely actually AAPLE per context at 00:04:12`). Keep `whisper_review_needed` flag.
   - **(c) Re-transcribe** → mark for re-ingestion with a larger Whisper model. Add `needs_retranscription` to `flags`.
   - **(d) Skip** → next file, no change.
4. Move to the next file.

---

## What NOT to do

- Don't modify transcript text. Even when the reviewer says "this should say X," the correction goes in `notes`, not in the transcript body. The source must remain faithful.
- Don't re-run Whisper from this skill. That's a separate operation (re-ingestion with a different model setting).
- Don't process files that aren't Whisper-sourced.

---

## When to run

- After every ingestion batch (or weekly cadence) to keep up with the Whisper backlog.
- Before sharing the corpus externally or before Layer 3 indexing — high-confidence content matters most for retrieval citation.
