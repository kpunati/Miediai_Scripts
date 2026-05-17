# AGENTS.md

Guidance for any LLM agent (Claude Code, Codex CLI, Gemini CLI, or other) opening this repository. Read this before doing anything in `/output`.

## What this repo is

A knowledge base of YouTube content from competitors and industry creators in the finance / marketing / management space. One markdown file per video in `/output`, structured for browsability now and for vector retrieval later.

See [README.md](./README.md) for structure, [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md) for full background.

## Source of truth

- **Project scope and decisions**: [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md)
- **Frontmatter schema (the contract)**: [schemas/frontmatter.schema.md](./schemas/frontmatter.schema.md)
- **Per-skill instructions**: [`/operations/<skill-name>/INSTRUCTIONS.md`](./operations/)

If anything in this file conflicts with PROJECT_CONTEXT.md, PROJECT_CONTEXT.md wins. If anything in a skill's INSTRUCTIONS.md is more specific than this file, the skill's instructions win for that skill.

## How to use the skills

Eight skills, each documented in `/operations/<name>/INSTRUCTIONS.md`. Run them by reading the relevant INSTRUCTIONS.md and executing what it describes against the corpus:

| Skill | When to invoke |
|---|---|
| `ingest` | User drops a channel URL or video URL — pull it into the catalog |
| `enrich` | Walk files where `enriched: false` and apply enrichment |
| `rebuild-index` | After ingestion batches or manual edits — refresh `output/index.csv` |
| `validate` | Before considering work "done" — schema/path/uniqueness checks |
| `status` | Quick "what's in the corpus" report |
| `review-whisper` | Surface Whisper-transcribed files for human spot-check |
| `re-enrich` | Force re-enrichment when enrichment instructions change |
| `export-for-embedding` | Generate retrieval-ready chunks (Layer 3 prep) |

If you're invoked without a clear skill — for example, the user just says "do the enrichment" — read the corresponding INSTRUCTIONS.md fully before starting.

## Hard rules

These exist because retrieval-readiness depends on them. Do not deviate without the user explicitly authorizing it.

1. **Never modify transcript text.** Captions and Whisper output are the source. Mistranscriptions get flagged in frontmatter (`flags: [whisper_review_needed]`), not corrected in-place. The corpus must reflect what was actually said.

2. **Frontmatter schema is the contract.** Add fields only if the user authorizes a schema change. Reserved enrichment slots (`summary`, `topics`, `entities`, etc.) exist on every file from ingest time — populate them; never delete or rename them.

3. **Filename convention is immutable**: `{channel_slug}_YYYY-MM-DD_{video_id}.md`. All three fields never change. Files don't move once written.

4. **Idempotency.** If `output/by-channel/{slug}/{date}_{video_id}.md` already exists, ingestion skips it. If `enriched: true`, enrichment skips it. Operations can be re-run safely.

5. **Enrichment is additive.** It writes to reserved frontmatter fields and may append a `## Enrichment Notes` section after the transcript. It never edits existing content.

6. **Timestamps stay in the transcript body.** Inline `[HH:MM:SS]` markers per caption cue or paragraph. Required for Layer 3 chunk-level citation. Don't strip them.

7. **One video = one file.** Never split a video across files or combine multiple videos into one.

## When to ask the user

- Schema changes (adding/removing/renaming frontmatter fields)
- Adding channels or videos that weren't explicitly authorized
- Anything that would touch files already in `/output` other than via the documented skill operations
- Anything ambiguous in an INSTRUCTIONS.md doc

## When NOT to ask

- Routine ingestion of a URL the user dropped
- Routine enrichment of files where `enriched: false`
- Running `validate`, `status`, `rebuild-index`, `review-whisper` (read-only or mechanical operations)

## Model-agnosticism

Every skill's INSTRUCTIONS.md is written to work with any capable LLM. If you notice the instructions assume Claude-specific features (tool names, slash commands, etc.), flag it — those belong in the thin wrapper at `.claude/skills/<name>/SKILL.md`, not in the canonical instructions.

## Logging and state

- Ingestion logs to `/logs/ingestion-{date}.log` (mode: append).
- Enrichment state lives in frontmatter (`enriched`, `enrichment_date`, `enrichment_version`). No separate database or state file.
- `output/index.csv` is derived state — always regeneratable from frontmatter via `rebuild-index`. Never edit it directly.

## Where things live (quick map)

- Want to add a channel? → `config/sources.csv`, then run `ingest`
- Want to expand the controlled vocabulary? → `config/taxonomy.md`
- Want to change what enrichment produces? → `operations/enrich/INSTRUCTIONS.md` and `operations/enrich/output_schema.md`
- Want to see what's in the corpus? → run `status` skill, or read `output/index.csv`
- Want to know if a video is already ingested? → check `output/by-channel/*/` for `*_{video_id}.md`
