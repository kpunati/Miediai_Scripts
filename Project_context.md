```markdown
# YouTube Transcript Ingestion — Project Context

## Background

Organization-wide initiative to build a knowledge base of competitor and 
industry YouTube content. This project covers YouTube only (TikTok is a 
later phase). Builds on a prior competitor-profiles repo that used a 
similar structure (README + templates + /output folder).

## Scope for v1 (this project)

**In scope:**
- Ingest YouTube videos from a curated list of channels
- Pull metadata (title, channel, date, duration, views, description, 
  native tags) via yt-dlp
- Pull transcripts via yt-dlp captions (manual preferred, auto fallback)
- For videos without captions: download audio and transcribe locally 
  with faster-whisper
- Output one markdown file per video with YAML frontmatter + transcript
- Sync /output to SharePoint/OneDrive (the "lake")
- Auto-generate a master index.csv from frontmatter across all files

**Explicitly out of scope for v1:**
- LLM enrichment (summaries, topic tags, classifications) — phase 2
- Vector indexing / RAG / semantic retrieval — phase 3
- TikTok ingestion — separate later project
- Deciding "what to do with the data" — management wants raw formatted 
  data first, use cases come after

**Deliverable for management:**
A populated /output folder synced to SharePoint, plus the repo itself 
showing the process. Files are structured, consistent, and queryable 
via the index.csv.

## Content domain

This corpus is primarily finance, financial advice, management, and 
marketing content from professional creators. Implications:
- Caption availability is expected to be high (>90%) — most videos won't 
  need Whisper
- Whisper accuracy on clearly-spoken professional speech is strong
- Known weak spot: tickers, fund names, specific dollar amounts, and 
  acronyms (401k, S&P, etc.) may be mistranscribed in BOTH auto-captions 
  AND Whisper output. Acceptable for knowledge-base purposes; flag for 
  review if specific claims are ever extracted as structured data.

## Legal/policy note

Competitor content is being stored for internal research and analysis 
only. Frontmatter includes a usage_policy field. Direct generation 
from this corpus is NOT a v1 goal — that decision is deferred.

## Repo structure

```
/yt-transcripts/
  README.md                    Project overview, schema, run instructions
  PROJECT_CONTEXT.md           This file
  /config/
    sources.csv                Channel list with per-channel config
    taxonomy.md                Placeholder for phase 2 controlled vocab
  /templates/
    transcript.template.md     Frontmatter schema + body structure
  /scripts/
    ingest.py                  Main ingestion: channels → videos → .md files
    build_index.py             Parses /output frontmatter → index.csv
  /output/                     The deliverable. Syncs to SharePoint.
    /by-channel/
      /{channel-slug}/
        YYYY-MM-DD_{video-id}.md
    index.csv                  Auto-generated master table
  /logs/
    ingestion-{date}.log
```

Filename convention: `YYYY-MM-DD_{video-id}.md`
(Title in filename breaks on special chars and path length limits.)

## Frontmatter schema (v1)

```yaml
---
video_id: dQw4w9WgXcQ
title: "Video title"
channel_name: "Channel name"
channel_id: UCxxxxxxxxxxxx
url: https://youtube.com/watch?v=...
publish_date: 2024-03-15
duration_seconds: 847
duration_human: "14:07"
view_count_at_ingest: 125432
description: |
  Original YouTube description, preserved verbatim.
language: en
transcript_source: auto_captions   # manual_captions, auto_captions, whisper, none
ingest_date: 2026-05-15
tags_youtube: [marketing, b2b]     # native YouTube tags
tags_topic: []                     # empty in v1, populated in phase 2
usage_policy: "research_only"
notes: ""
---

# {title}

**Channel:** {channel_name}
**Published:** {publish_date}
**URL:** {url}

## Description
{description}

## Transcript
{transcript_body}
```

Keep `tags_topic` in schema even though empty — adding fields to 500 files 
later is painful, empty arrays are free now.

## sources.csv format

```
channel_url,exclude_shorts,min_duration_sec,since_date,notes
https://youtube.com/@competitor-a,true,90,2023-01-01,primary competitor
https://youtube.com/@competitor-b,true,90,2024-01-01,recent pivot only
```

Per-channel config in CSV (not code) so tuning doesn't require edits.

## Required environment

- Python 3.10+
- Tools:
  - `yt-dlp` (primary — metadata + captions + audio fallback)
  - `faster-whisper` (local transcription fallback)
  - `python-frontmatter`, `pyyaml`, `pandas` (file handling + index generation)
- Whisper model: `medium` (good balance of speed/accuracy for clearly-spoken 
  professional content; auto-downloads on first use, ~1.5GB)
- No YouTube Data API key needed — yt-dlp pulls metadata directly
- Disk space: budget ~5GB for whisper model + temp audio files during runs

## Channel-to-video processing rules

1. For each channel in sources.csv:
   - Use yt-dlp to enumerate all videos in the channel's uploads
   - Apply filters: exclude_shorts (default true), min_duration_sec 
     (default 90), since_date (default 3 years back)

2. For each video that passes filters:
   - Use yt-dlp to fetch metadata as JSON
   - Try caption pull (manual captions preferred, auto-generated as 
     fallback). Set `transcript_source: manual_captions` or `auto_captions`
   - If no captions available:
     - yt-dlp downloads audio-only (mp3 or m4a, lowest acceptable bitrate)
     - faster-whisper transcribes locally with the medium model
     - Set `transcript_source: whisper`
     - Delete temp audio file after transcription
   - Write .md file using template

3. Always-on logging:
   - Per-video: status (success/skip/fail), transcript_source, duration, 
     processing time
   - Log Whisper-transcribed videos prominently — candidates for 
     spot-check review

4. After full run: regenerate index.csv via build_index.py

## Order of operations

1. Scaffold repo (README, folder structure, empty configs, template file)
2. Hand-build one example .md file from a real video to validate template 
   ← do this BEFORE writing scripts
3. Write ingest.py, test against ONE channel first
4. Write build_index.py
5. Validate output with team
6. Run full ingestion across all channels in sources.csv
7. Set up SharePoint sync on /output

## Open questions / decisions deferred

- Final list of channels: user has an Excel sheet, will be converted to 
  sources.csv
- Per-channel since_date overrides: decide during pilot
- Phase 2 enrichment taxonomy: separate project, don't pre-optimize

## What I want from you (the IDE assistant)

Start by scaffolding the repo per the structure above: README.md, the 
folder tree, the transcript template, an empty sources.csv with header 
row, and a stub taxonomy.md. Don't write the Python scripts yet — I 
want to hand-build one example transcript file first to validate the 
schema works against real content.
```

Want me to also save this as an actual `.md` file you can download, or is the inline copy enough for moving over?