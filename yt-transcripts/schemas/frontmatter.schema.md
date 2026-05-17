# Frontmatter Schema (canonical contract)

Every `.md` file under `/output/by-channel/` must conform to this schema. This file is the single source of truth — templates and validation logic derive from it.

## Schema (with types and population stage)

| Field | Type | Set at | Required | Description |
|---|---|---|---|---|
| `video_id` | string | ingest | yes | YouTube video ID (11 chars). Stable, never changes. |
| `url` | string (URL) | ingest | yes | Canonical YouTube watch URL. |
| `title` | string | ingest | yes | Video title as published. |
| `channel_name` | string | ingest | yes | Channel display name. |
| `channel_id` | string | ingest | yes | YouTube channel ID. |
| `channel_slug` | string | ingest | yes | Filesystem-safe slug derived from channel name (lowercase, hyphens). |
| `publish_date` | date (YYYY-MM-DD) | ingest | yes | UTC date the video was published. |
| `duration_seconds` | int | ingest | yes | Total duration in seconds. |
| `duration_human` | string | ingest | yes | Human-readable duration (e.g. `"14:07"`). |
| `view_count_at_ingest` | int | ingest | yes | View count at time of ingestion (does not get updated). |
| `language` | string | ingest | yes | ISO 639-1 language code (e.g. `en`). |
| `description` | string (block) | ingest | yes | Original YouTube description, preserved verbatim. |
| `tags_youtube` | list of string | ingest | yes | Native YouTube tags as provided by the channel. |
| `transcript_source` | enum | ingest | yes | One of: `manual_captions`, `auto_captions`, `whisper`, `none`. |
| `transcript_has_timestamps` | bool | ingest | yes | `true` if body has inline `[HH:MM:SS]` markers. |
| `ingest_date` | date | ingest | yes | Date the file was created. |
| `ingest_version` | int | ingest | yes | Bump if ingestion logic changes materially. Starts at `1`. |
| `enriched` | bool | ingest | yes | `false` at ingest time. Flipped to `true` after enrichment. |
| `enrichment_date` | date \| null | enrich | yes | Null until enriched. |
| `enrichment_version` | int \| null | enrich | yes | Null until enriched. Bump if enrichment instructions change materially. |
| `summary` | string | enrich | yes | 1–3 sentence summary. Empty string at ingest. |
| `topics` | list of string | enrich | yes | Topics from `config/taxonomy.md` (controlled). Empty list at ingest. |
| `topics_proposed` | list of string | enrich | yes | Topics not yet in the controlled vocab. Empty list at ingest. |
| `entities` | object | enrich | yes | Structured entities (see below). Empty arrays at ingest. |
| `content_type` | string | enrich | yes | One of `taxonomy.md`'s content types. Empty string at ingest. |
| `audience_level` | string | enrich | yes | One of `taxonomy.md`'s audience levels. Empty string at ingest. |
| `key_claims` | list of object | enrich | yes | Notable claims with timestamps (see below). Empty list at ingest. |
| `tags_topic` | list of string | enrich | yes | Reserved alias for `topics` from the original spec — kept for backward compat. Mirror of `topics`. |
| `usage_policy` | string | ingest | yes | Always `"research_only"` for v1. |
| `flags` | list of string | both | yes | E.g. `["whisper_review_needed"]`, `["unpunctuated_captions"]`, `["enrichment_failed"]`. Empty list by default. See [operations/ingest/INSTRUCTIONS.md](../operations/ingest/INSTRUCTIONS.md) and [operations/enrich/INSTRUCTIONS.md](../operations/enrich/INSTRUCTIONS.md) for when each flag is added. |
| `notes` | string | manual | yes | Free-text human notes. Empty string by default. |

### Nested: `entities`

```yaml
entities:
  people: []      # list of {name: string, role?: string}
  companies: []   # list of {name: string, ticker?: string}
  tickers: []     # list of string (e.g. "AAPL")
  funds: []       # list of {name: string, ticker?: string}
  products: []    # list of string
  concepts: []    # list of string (e.g. "dollar-cost-averaging")
```

### Nested: `key_claims`

```yaml
key_claims:
  - claim: "Index funds outperform actively managed funds 80% of the time over 20 years"
    timestamp: "00:04:12"
    confidence: "medium"   # high | medium | low
    flagged: false         # true if claim involves a specific number/ticker prone to mistranscription
```

## Body structure

After frontmatter, the body has different sections depending on whether the file is enriched.

**At ingest time** (just header + transcript). The video description lives only in frontmatter — not duplicated in the body.

```markdown
# {title}

**Channel:** {channel_name}
**Published:** {publish_date}
**URL:** {url}
**Duration:** {duration_human}

## Transcript

[00:00:00] First chunk of transcript text…

[00:00:30] Next chunk…

…
```

**After enrichment** (header + three required readable sections + transcript). Enrichment INSERTS three sections between the header block and `## Transcript`:

```markdown
# {title}

**Channel:** {channel_name}
**Published:** {publish_date}
**URL:** {url}
**Duration:** {duration_human}

## Summary

<2-4 sentence readable paragraph>

## Key Takeaways

- Bullet
- Bullet
- ... (4-7 bullets)

## Detailed Notes

### Section heading [HH:MM:SS]
<1-4 sentence notes>

### Next section heading [HH:MM:SS]
<more notes>

…

## Transcript

[00:00:00] …
```

See [operations/enrich/INSTRUCTIONS.md](../operations/enrich/INSTRUCTIONS.md) → "Body sections" for content rules.

Optionally, an `## Enrichment Notes` section may be appended after `## Transcript`:

```markdown
## Enrichment Notes

Optional free-form notes from the enrichment pass.
Brief, only when the structured fields can't capture something material.
```

## Validation rules (enforced by `validate` skill)

1. Every required field present.
2. Types match.
3. Enum values valid (`transcript_source`, `content_type`, `audience_level`, `flags`).
4. `video_id` is unique across the entire `/output` tree.
5. Filename matches `{channel_slug}_YYYY-MM-DD_{video_id}.md` and lives in `output/by-channel/{channel_slug}/`.
6. Filename date matches `publish_date`.
7. `transcript_has_timestamps: true` implies at least one `[HH:MM:SS]` marker exists in the transcript body.
8. If `enriched: true`, then `enrichment_date`, `enrichment_version`, `summary` are non-null/non-empty.
9. `topics_proposed` items do not appear in `topics` (no duplicates across controlled and proposed).
10. `tags_topic` mirrors `topics` (until the alias is dropped).
