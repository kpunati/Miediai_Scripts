---
name: validate
description: Walk the corpus and check every .md file conforms to the frontmatter schema, path conventions, uniqueness, and timestamp requirements. Read-only — surfaces issues, doesn't fix them.
---

# validate

Thin Claude Code wrapper for the **validate** operation. Source of truth: [`/operations/validate/INSTRUCTIONS.md`](../../../operations/validate/INSTRUCTIONS.md). Schema authority: [`/schemas/frontmatter.schema.md`](../../../schemas/frontmatter.schema.md).

## How to use

Invoke `scripts/validate_corpus.py` (once implemented). No arguments. Surface the report grouped by ERRORS / WARNINGS / STATS.

If the script is still stubbed, do the work directly: walk `/output/by-channel/**/*.md`, parse each file, run the checks listed in the instructions doc.

## Hard rules

- Strictly read-only. Never modifies files.
- Don't auto-fix. Report issues so the user decides what to do.
- Exit non-zero if any ERROR is found (helps catch issues in CI later).
