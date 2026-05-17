---
name: export-for-embedding
description: Convert the enriched corpus into chunks ready for vector embedding. Layer 3 prep — produces JSONL with inherited frontmatter per chunk. Does not call any LLM or embedding provider.
---

# export-for-embedding

Thin Claude Code wrapper for the **export-for-embedding** operation. Source of truth: [`/operations/export-for-embedding/INSTRUCTIONS.md`](../../../operations/export-for-embedding/INSTRUCTIONS.md).

## How to use

Default to dry-run first — invoke `scripts/export_chunks.py --dry-run` (once implemented) and show the user the chunk count, distribution, and any skipped files. After they review, run without `--dry-run` to actually write `output/chunks.jsonl`.

## Hard rules

- No LLM calls. No embedding-provider calls. This skill produces input for a future Layer 3, nothing more.
- Read-only against `.md` files.
- Output goes to `output/chunks.jsonl` (not committed to the repo — see `.gitignore`).
- Skip files where `transcript_has_timestamps: false` or `transcript_source: none` — log the skips.
