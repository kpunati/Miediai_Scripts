---
name: enrich
description: Walk transcript files where enriched is false and populate summary, topics, entities, content_type, audience_level, and key_claims per the model-agnostic enrichment instructions. The core distributed-enrichment workflow — runs from any capable CLI.
---

# enrich

Thin Claude Code wrapper for the **enrich** operation. Source of truth is [`/operations/enrich/INSTRUCTIONS.md`](../../../operations/enrich/INSTRUCTIONS.md) and the strict schema in [`/operations/enrich/output_schema.md`](../../../operations/enrich/output_schema.md).

## How to use

When the user says "enrich the next N files," "enrich {channel-slug}," "enrich video {id}," or "enrich everything":

1. **Read both** [`/operations/enrich/INSTRUCTIONS.md`](../../../operations/enrich/INSTRUCTIONS.md) and [`/operations/enrich/output_schema.md`](../../../operations/enrich/output_schema.md) fully if you haven't this session. The instructions are intentionally detailed — don't skim.
2. Also read [`/config/taxonomy.md`](../../../config/taxonomy.md) before each batch to get the current controlled vocab.
3. Process per the per-file workflow in INSTRUCTIONS.md.
4. **Auto-run validate** after the batch: `source .venv/bin/activate && python scripts/validate_corpus.py`. Surface any errors and offer to fix.
5. **Auto-run rebuild-index** after validate passes: `python scripts/build_index.py`.
6. Report the batch summary; offer to run `review-whisper` on any files that now have `whisper_review_needed` flag.

## Important

- This skill IS the worker — you (the agent) are doing the enrichment, not invoking an external script.
- The output schema is strict. Validate against it before writing each file.
- Original transcript text is never modified — only frontmatter fields and optionally a `## Enrichment Notes` section.
- If the user runs this from Codex or Gemini instead, the same INSTRUCTIONS.md drives them. Don't add Claude-specific logic that diverges.

## Default behavior

If the user just says "enrich" with no count or selector: process the next 5 unenriched files (oldest by `ingest_date`) and report back. They can ask for more.
