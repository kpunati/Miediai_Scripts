---
name: status
description: Quick dashboard report on the corpus — total counts, by-channel breakdown, enrichment percentage, transcript source distribution, recent additions, flagged files.
---

# status

Thin Claude Code wrapper for the **status** operation. Source of truth: [`/operations/status/INSTRUCTIONS.md`](../../../operations/status/INSTRUCTIONS.md).

## How to use

Invoke `scripts/corpus_status.py` (once implemented). Format the output nicely for the user. If the user asks for it as a management-facing summary, add a brief narrative on top.

If the script is still stubbed, walk `/output/by-channel/` directly and compile the sections from the instructions doc.

## Hard rules

- Read-only.
- Handle empty corpus gracefully ("no videos yet").
