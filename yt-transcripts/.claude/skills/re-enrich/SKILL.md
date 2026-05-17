---
name: re-enrich
description: Force re-enrichment on selected files when the enrichment instructions or schema have changed. Two-step — marks files as enriched=false, then optionally triggers the enrich skill.
---

# re-enrich

Thin Claude Code wrapper for the **re-enrich** operation. Source of truth: [`/operations/re-enrich/INSTRUCTIONS.md`](../../../operations/re-enrich/INSTRUCTIONS.md).

## How to use

Take a selector from the user (`--all`, `--channel {slug}`, `--video {id}`, or `--enrichment-version {n}`):

1. Confirm with the user (re-enrichment costs CLI-session time even if no API cost).
2. Invoke `scripts/mark_unenriched.py` with the selector (once implemented) — this preserves existing enrichment values while setting `enriched: false`.
3. Ask the user if they want to trigger `enrich` now or later.
4. If `enrich` runs in the same session, its own SKILL wrapper will auto-validate and auto-rebuild-index.
5. If the user defers `enrich`, still **auto-run validate** to confirm the marking step didn't break the schema.

If the script is still stubbed, do the work directly: walk matching files and update their frontmatter.

## Hard rules

- Don't clear existing enrichment field values — preserves a fallback if re-enrichment fails.
- Confirm before processing more than ~50 files.
