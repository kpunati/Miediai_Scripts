---
name: review-whisper
description: Surface Whisper-transcribed files for human spot-check, sorted by view count. Optionally walks the user through each file interactively to confirm, flag, or mark for re-transcription.
---

# review-whisper

Thin Claude Code wrapper for the **review-whisper** operation. Source of truth: [`/operations/review-whisper/INSTRUCTIONS.md`](../../../operations/review-whisper/INSTRUCTIONS.md).

## How to use

Two modes:

- **List**: invoke `scripts/list_whisper.py` (once implemented) and show the ranked list.
- **Walkthrough**: take the ranked list and walk the user through each file interactively. For each, display key metadata + extracted entities/claims (if enriched), then prompt for confirm / flag / re-transcribe / skip. Update the file's `notes` and `flags` per the user's call.

## Hard rules

- Never modify transcript text. Corrections go in `notes`, not the transcript body.
- Don't run Whisper from this skill. Re-transcription is a separate ingestion operation.
