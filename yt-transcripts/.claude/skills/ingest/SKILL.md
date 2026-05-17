---
name: ingest
description: Ingest a YouTube channel or video URL into the catalog — pulls metadata, transcript (captions or Whisper), writes a structured .md file with full frontmatter to output/by-channel/.
---

# ingest

Thin Claude Code wrapper for the **ingest** operation. Source of truth is [`/operations/ingest/INSTRUCTIONS.md`](../../../operations/ingest/INSTRUCTIONS.md) at the repo root.

## How to use

When the user drops a YouTube URL (channel or video):

1. Read [`/operations/ingest/INSTRUCTIONS.md`](../../../operations/ingest/INSTRUCTIONS.md) fully if you haven't this session.
2. Auto-detect channel vs video from the URL.
3. If a channel and not in `config/sources.csv`, the script auto-appends a default row; surface that to the user so they can edit it.
4. Activate the venv and invoke: `source .venv/bin/activate && python scripts/ingest.py {url}`.
5. **Auto-run validate** on the corpus after ingest: `python scripts/validate_corpus.py`. Surface any errors.
6. **Auto-run rebuild-index**: `python scripts/build_index.py`. This refreshes `output/index.csv` so the new file is queryable.
7. Report all results; suggest enrichment of the new file(s) if the user wants to continue the pipeline.

## Hard rules (reminder)

- Idempotent: skip if file already exists.
- Never modify transcript text.
- Always write filenames as `{channel_slug}_YYYY-MM-DD_{video_id}.md`.
- Delete temp audio after Whisper.

Full rules and the per-video workflow live in the canonical instructions doc — defer to it.
