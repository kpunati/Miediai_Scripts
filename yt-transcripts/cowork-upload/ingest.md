# Skill: ingest

**Purpose**: Take a YouTube URL (channel or video), pull metadata + transcript, and write a structured `.md` file into `/output/by-channel/{slug}/`.

**Input**: A YouTube URL — either a channel URL (`youtube.com/@name` or `/channel/UC...`) or a single video URL (`youtube.com/watch?v=...` or `youtu.be/...`).

**Output**: One `.md` file per video in `output/by-channel/{channel_slug}/{channel_slug}_YYYY-MM-DD_{video_id}.md`, conforming to [`schemas/frontmatter.schema.md`](../../schemas/frontmatter.schema.md). Log line per video in `/logs/ingestion-{date}.log`.

---

## How to run

The agent or the user invokes this skill with a URL. The skill (or its Python backing in `scripts/ingest.py`) does the work — see [`PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md) → "Channel-to-video processing rules" for the canonical processing flow.

### Auto-detect URL type

- Contains `/watch?v=` or `youtu.be/` → single video
- Contains `/@`, `/channel/`, `/c/`, `/user/` → channel
- Ambiguous → ask the user

### Channel flow

1. If channel not in `config/sources.csv`, append a row with sensible defaults:
   - `channel_slug`: lowercase, hyphens, derived from the channel handle/name
   - `exclude_shorts`: `true`
   - `min_duration_sec`: `90`
   - `since_date`: 3 years before today
   - `notes`: empty (user can fill in later)
   Then confirm the row with the user before proceeding.
2. Enumerate channel uploads via yt-dlp.
3. Apply filters from the channel's row.
4. For each surviving video, run the video flow (below).
5. After the batch: suggest running `rebuild-index`.

### Video flow (per video)

1. **Idempotency check**: if `output/by-channel/{slug}/{slug}_{YYYY-MM-DD}_{video_id}.md` already exists, skip and log `skip:exists`. (Idempotency is keyed on `video_id` — date or slug changes shouldn't cause a duplicate; if for some reason an older filename format exists for the same `video_id`, skip and log `skip:legacy_filename`.)
2. **Fetch metadata** via yt-dlp as JSON.
3. **Try captions** in this order:
   - Manual captions (`writesubtitles`, language preference: `en` then any) → set `transcript_source: manual_captions`.
   - Auto-generated captions → set `transcript_source: auto_captions`.
4. **If no captions**:
   - Download audio-only (mp3 or m4a, lowest acceptable bitrate) to a temp folder.
   - Transcribe with `faster-whisper` (model: `medium`).
   - Delete the audio file immediately after transcription.
   - Set `transcript_source: whisper`.
   - Add `whisper_review_needed` to `flags`.
5. **Format the transcript body** with inline `[HH:MM:SS]` timestamps:
   - From VTT/SRT captions: use cue start times.
   - From Whisper: use segment start times.
   - **Sentence-aware paragraph grouping**: target ~30 seconds per paragraph, but never close a paragraph mid-sentence. Once the elapsed time within the current paragraph reaches 30s, keep appending cues until the accumulated text ends with sentence-ending punctuation (`.`, `!`, `?`, optionally followed by quotes/brackets). Then close the paragraph and start a new one at the next cue.
   - **Fallback for unpunctuated captions**: YouTube auto-captions on older videos (pre-2024-ish) often omit punctuation entirely. If 60 seconds elapse within the current paragraph without finding a sentence boundary, hard-break anyway. Track how many paragraphs used the fallback during a single file's processing — if more than 50% did, add the `unpunctuated_captions` flag to `flags` so downstream consumers know the transcript lacks natural sentence boundaries. This flag is informational (sets reader expectations, may signal lower confidence for enrichment claim extraction); it does not block any operation.
   - For YouTube auto-caption VTT files: each cue contains rolling text plus inline word-timing tags (`<HH:MM:SS.fff><c>word</c>`). Extract only the line with `<c>` tags per cue and strip the inline timing markers — those represent the "new content" for that cue. Skip cues that are pure carry-over from the prior cue.
   - HTML entities (`&amp;`, `&#39;`, etc.) in caption text must be decoded.
   - Preserve text exactly as the source produces it. Do not re-punctuate or "clean up" what the captioner produced (mistranscriptions get surfaced by `review-whisper` and enrichment flags, not corrected here).
6. **Render** the file using `templates/transcript.template.md`.
7. **Validate** frontmatter against the schema (fail loudly if any required field is missing).
8. **Write** to the target path. Set `transcript_has_timestamps: true`.
9. **Log** one line: `{ts} {video_id} status={success|skip|fail} source={...} duration={s} processed_in={s}`.

---

## Filters (per channel)

Read from `config/sources.csv`. Defaults if missing:

- `exclude_shorts: true` (videos < 60s and YouTube Shorts)
- `min_duration_sec: 90`
- `since_date: today - 3 years`

**Filters apply only during channel enumeration — not when the user explicitly names a single video URL.** The reasoning: when someone drops a specific video, *they* are the curator; the filter exists to prevent channel-wide bulk runs from including unwanted content (shorts, ancient videos, etc.). Applying it to user-named videos creates surprising "why didn't this ingest?" failures.

User can override per-channel in `sources.csv`.

---

## What NOT to do

- Don't ingest channels not in `sources.csv` without first appending them (and confirming with user).
- Don't overwrite existing files. Idempotency is non-negotiable.
- Don't ingest videos that fail the filters (no shorts, respect min duration and since_date).
- Don't strip or normalize transcript text. Source fidelity matters for retrieval citation.
- Don't leave temp audio files behind.

---

## Failure handling

- yt-dlp failures (rate-limited, video unavailable, deleted): log `fail:{reason}`, continue with the next video.
- Whisper failures (corrupted audio, OOM): log `fail:whisper:{reason}`, leave no file behind.
- Network failures: retry once with backoff; if still failing, log and continue.

After the batch, summarize: total processed, successes, skips, failures. Surface failed video IDs for the user to optionally retry.

---

## Backing script

`scripts/ingest.py` does the mechanical work. The skill's role from the agent side is mostly: detect URL type, validate `sources.csv` row exists, invoke the script, surface the results, and suggest the natural next step (`rebuild-index`).
