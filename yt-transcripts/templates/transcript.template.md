---
# === Identifiers (immutable, set at ingest) ===
video_id: "{{video_id}}"
url: "https://youtube.com/watch?v={{video_id}}"

# === Core metadata (set at ingest) ===
title: "{{title}}"
channel_name: "{{channel_name}}"
channel_id: "{{channel_id}}"
channel_slug: "{{channel_slug}}"
publish_date: {{publish_date}}        # YYYY-MM-DD
duration_seconds: {{duration_seconds}}
duration_human: "{{duration_human}}"  # e.g. "14:07"
view_count_at_ingest: {{view_count_at_ingest}}
language: "{{language}}"              # ISO 639-1, e.g. "en"

# === Original content (preserved verbatim) ===
description: |
  {{description}}
tags_youtube: {{tags_youtube}}        # native YouTube tags, list of string

# === Transcript provenance ===
transcript_source: "{{transcript_source}}"  # manual_captions | auto_captions | whisper | none
transcript_has_timestamps: {{transcript_has_timestamps}}
ingest_date: {{ingest_date}}                # YYYY-MM-DD
ingest_version: 1

# === Enrichment state (populated by enrich skill) ===
enriched: false
enrichment_date: null
enrichment_version: null
summary: ""
topics: []
topics_proposed: []
entities:
  people: []
  companies: []
  tickers: []
  funds: []
  products: []
  concepts: []
content_type: ""
audience_level: ""
key_claims: []
tags_topic: []                        # alias for topics — keep mirrored

# === Governance ===
usage_policy: "research_only"
flags: []                             # e.g. ["whisper_review_needed"]
notes: ""
---

# {{title}}

**Channel:** {{channel_name}}
**Published:** {{publish_date}}
**URL:** https://youtube.com/watch?v={{video_id}}
**Duration:** {{duration_human}}

<!--
The video description lives in the frontmatter `description:` field only.
It's not duplicated in the body — keeps files focused on the transcript
(which is the retrieval-relevant content) and avoids redundant maintenance.
Tools that need the description read it from frontmatter; index.csv
surfaces it for browse/search.
-->

## Transcript

{{transcript_body}}

<!--
Transcript body format:

[00:00:00] First chunk of speech, captured as a readable paragraph.
Several sentences worth of content here. Keep punctuation as-is from
the caption/Whisper source — do not edit.

[00:00:30] Next chunk, again with leading timestamp marker.

…

Timestamps are inline at the start of each cue or natural paragraph.
Required for retrieval — never strip them.
-->
