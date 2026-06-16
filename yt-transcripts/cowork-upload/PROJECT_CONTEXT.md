# YouTube Transcript Ingestion — Project Context

## Background

Organization-wide initiative to build a knowledge base of competitor and industry YouTube content. This project covers YouTube only (TikTok is a separate later project). Builds on a prior competitor-profiles repo that used a similar structure (README + templates + `/output` folder).

## Scope

This is a **single complete system**, not a versioned product. Three layers, built in dependency order, all in scope:

**Layer 1 — Ingestion** (build first, foundation)
- Ingest YouTube videos from a curated list of channels (and ad-hoc individual videos)
- Pull metadata (title, channel, date, duration, views, description, native tags) via yt-dlp
- Pull transcripts via yt-dlp captions (manual preferred, auto fallback)
- For videos without captions: download audio and transcribe locally with faster-whisper
- Output one markdown file per video with YAML frontmatter + transcript (with inline timestamps)
- Auto-generate a master `index.csv` from frontmatter across all files

**Layer 2 — Enrichment** (build after ingestion is solid)
- LLM-driven enrichment pass: summary, topic tags, entities (people/companies/tickers/funds/concepts), content type, audience level, key claims with timestamps
- Distributed model: anyone in the org with the repo runs the `enrich` skill from their preferred CLI
- Idempotent — `enriched: true/false` flag on each file gates re-runs
- Enrichment is additive — never modifies the original transcript text

**Layer 3 — Retrieval** (deferred until API budget is confirmed)
- Chunk transcripts into retrieval units (timestamps preserved so chunks link to moments)
- Embed chunks via a managed provider (commitment: choosing an embedding provider is one-way)
- Hosted query interface that returns cited answers
- Layers 1 and 2 are structured to be retrieval-ready, so Layer 3 can be added without re-processing existing files

**Out of scope:**
- TikTok ingestion (separate later project)
- Direct content generation from this corpus (not a v1 goal; usage policy on every file is `research_only`)

## Content domain

Primarily finance, financial advice, management, and marketing content from professional creators. Implications:
- Caption availability is expected to be high (>90%) — most videos won't need Whisper
- Whisper accuracy on clearly-spoken professional speech is strong
- **Known weak spot**: tickers, fund names, specific dollar amounts, and acronyms (401k, S&P, etc.) may be mistranscribed in BOTH auto-captions AND Whisper output. Acceptable for knowledge-base purposes; the `review-whisper` skill surfaces these files for spot-check, and any structured-data extraction (e.g. in enrichment's `key_claims`) should flag low-confidence values.

## Legal / policy

Competitor content is stored for internal research and analysis only. Frontmatter includes a `usage_policy: research_only` field on every file. Direct generation from this corpus is not currently authorized.

## Workflow model

The user adds content to the catalog incrementally — dropping channel URLs (or occasional individual video URLs) one or a few at a time, rather than batch-ingesting from a master sheet. This means:

- `ingest` accepts either a channel URL or a video URL and auto-detects which.
- All operations are **idempotent**: skip files where `{date}_{video_id}.md` already exists; skip enrichment where `enriched: true`.
- `sources.csv` grows organically as channels are added.

The user has an Excel sheet of curated channels that will be migrated to `sources.csv` over time, but not as a single bulk operation.

## Retrieval-readiness requirements

Layer 3 isn't built yet, but Layers 1 and 2 must produce data that's directly indexable when Layer 3 starts. The structural commitments:

1. **Stable unique IDs.** `video_id` from YouTube is the anchor. Chunk IDs derived from it.
2. **Timestamped transcript body.** Inline `[HH:MM:SS]` markers per cue/paragraph. Enables moment-level citation in retrieval.
3. **Rich, uniform frontmatter on every file.** Chunks inherit file frontmatter as context for hybrid filtering.
4. **Reserved frontmatter slots for enrichment output.** Empty fields (`summary: ""`, `topics: []`, `entities: {...}`) exist from ingest time — no schema migration on hundreds of files later.
5. **Transcript text is never modified.** Only additive enrichment. Mistranscriptions are flagged in metadata, not corrected in-place.
6. **One video = one file, path immutable.** `{channel_slug}_YYYY-MM-DD_{video_id}.md` in `output/by-channel/{slug}/`. Channel slug, date, and video_id are all stable.

See [schemas/frontmatter.schema.md](./schemas/frontmatter.schema.md) for the full schema contract.

## Repo structure

See [README.md](./README.md) for the folder tree.

Filename convention: `{channel_slug}_YYYY-MM-DD_{video_id}.md`
(Title in filename breaks on special chars and path length limits. Including the channel slug makes the filename self-describing if a file is moved or copied out of its `by-channel/` folder; the full video_id preserves URL reconstruction and avoids collisions.)

## Required environment

- Python 3.10+
- Tools:
  - `yt-dlp` (metadata + captions + audio fallback)
  - `faster-whisper` (local transcription fallback)
  - `python-frontmatter`, `pyyaml`, `pandas` (file handling + index generation)
- Whisper model: `medium` initially; revisit during pilot if accuracy on finance terms is unacceptable (consider `large-v3`).
- No YouTube Data API key needed — yt-dlp pulls metadata directly.
- Disk space: budget ~5GB for whisper model + temp audio files during runs.

## Output destination

`/output` is the deliverable. It will eventually sync to SharePoint. The sync mechanism (OneDrive folder mount, rclone, Power Automate, or manual upload) is deferred — pick once the catalog has shape.

## LLM access model

- **Ingestion**: no LLM. yt-dlp + Whisper run locally.
- **Enrichment**: runs through whoever in the org has the repo and a CLI (Claude Code, Codex CLI, Gemini CLI). Uses their existing subscription. Zero marginal API cost. Instructions in `/operations/enrich/INSTRUCTIONS.md` are model-agnostic.
- **Retrieval (Layer 3, deferred)**: requires API access — subscriptions can't power a backend endpoint. Budget for one LLM API key (Claude / GPT / Gemini for answering) + one embedding provider key. Total cost at expected scale: under $50/month.

## Channel-to-video processing rules

1. For each channel in `sources.csv`:
   - Use yt-dlp to enumerate all videos in the channel's uploads
   - Apply filters: `exclude_shorts` (default true), `min_duration_sec` (default 90), `since_date` (default 3 years back)

2. For each video that passes filters:
   - Use yt-dlp to fetch metadata as JSON
   - Try caption pull (manual captions preferred, auto-generated as fallback). Set `transcript_source: manual_captions` or `auto_captions`.
   - If no captions available:
     - yt-dlp downloads audio-only (mp3 or m4a, lowest acceptable bitrate)
     - faster-whisper transcribes locally with the medium model
     - Set `transcript_source: whisper`
     - Delete temp audio file after transcription
   - Write `.md` file using `/templates/transcript.template.md`

3. Always-on logging in `/logs/ingestion-{date}.log`:
   - Per-video: status (success/skip/fail), transcript_source, duration, processing time
   - Log Whisper-transcribed videos prominently — candidates for `review-whisper`

4. After ingestion batch: run `rebuild-index` to refresh `output/index.csv`.

## Order of operations

1. ✅ Scaffold repo
2. Hand-build one example `.md` file from a real video to validate template — **do this BEFORE writing scripts**
3. Implement `scripts/ingest.py`, test against ONE channel first
4. Implement `scripts/build_index.py`
5. Validate output with team
6. Run `enrich` skill on pilot files to validate enrichment instructions
7. Full ingestion across `sources.csv`
8. Set up SharePoint sync on `/output`
9. (Later) Layer 3 — vector indexing + query interface

## Open decisions

- **SharePoint sync mechanism**: deferred until catalog has shape
- **Whisper model size**: start with `medium`, revisit after spot-checking pilot output
- **Layer 3 architecture** (vector store, embedding provider, query interface): deferred until budget confirmed
- **Phase 2 enrichment taxonomy**: `config/taxonomy.md` grows as enrichment runs surface common themes; don't pre-optimize
