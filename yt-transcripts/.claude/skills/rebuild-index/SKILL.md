---
name: rebuild-index
description: Regenerate output/index.csv by walking every .md file and extracting selected frontmatter fields. Mechanical operation, run after ingestion or enrichment batches.
---

# rebuild-index

Thin Claude Code wrapper for the **rebuild-index** operation. Source of truth: [`/operations/rebuild-index/INSTRUCTIONS.md`](../../../operations/rebuild-index/INSTRUCTIONS.md).

## How to use

Invoke `scripts/build_index.py` (once implemented). No arguments. Report the result — total files indexed, any parse failures.

If the script is still stubbed, do the work directly: walk `/output/by-channel/**/*.md`, parse frontmatter, emit `output/index.csv` per the column list in the instructions doc.

## Hard rules

- Read-only against `.md` files.
- Overwrites `output/index.csv` — that file is derived state.
- If any file fails to parse, log it but continue; don't abort the whole run.
