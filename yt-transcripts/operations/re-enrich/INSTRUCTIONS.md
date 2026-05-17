# Skill: re-enrich

**Purpose**: Force re-enrichment on selected files. Used when enrichment instructions or the output schema change — existing enriched files become stale and need refreshing.

**Input**: A selector (one of `--all`, `--channel {slug}`, `--video {video_id}`, `--enrichment-version {n}` to target files at a specific older version).

**Output**: Selected files have `enriched: false` set, ready for the `enrich` skill to re-process. Optionally invokes `enrich` immediately.

---

## How to run

Two-step workflow:

1. **Mark** selected files as unenriched. The mechanical step — `scripts/mark_unenriched.py` flips `enriched: false` on the matching files. Other enrichment fields are preserved (in case the re-enrichment is interrupted, you don't lose the old values).
2. **Re-run** `enrich` skill on the same selector. The enrich skill skips files with `enriched: true` and processes everything else.

Confirm with the user before marking — re-enrichment loses no data but does mean re-spending CLI-session time.

---

## Selector semantics

- `--all` — every enriched file in the corpus. Use when enrichment instructions changed materially.
- `--channel {slug}` — every enriched file under that channel.
- `--video {video_id}` — one file.
- `--enrichment-version {n}` — every file with `enrichment_version: n` (so you can target only the truly stale ones).

If multiple selectors are passed, the intersection applies.

---

## Behavior

For each matching file:
1. Keep all existing enrichment field values (summary, topics, entities, etc.) in place — don't clear them.
2. Set `enriched: false`.
3. Set `enrichment_version: null`.
4. Set `enrichment_date: null`.

This way the previous enrichment is still visible (and usable as a baseline) until the re-enrichment overwrites it. If the re-enrichment is interrupted, the file is in a known state: `enriched: false` but with prior-pass data still readable.

After marking: log the count of files marked and tell the user to run `enrich` next.

---

## When to bump `enrichment_version`

Update the version number in `operations/enrich/output_schema.md` and the value the `enrich` skill writes when:
- A new field is added to enrichment output.
- A field's meaning or scope changes.
- Validation rules tighten.
- The taxonomy is materially expanded (so existing files should map old proposed topics to new controlled ones).

Cosmetic prompt tweaks don't warrant a version bump.

---

## What NOT to do

- Don't delete enrichment field values when marking — preserves a fallback if re-enrichment fails.
- Don't re-enrich files that are still at the current version (no work to do).
- Don't trigger re-enrichment of more than ~50 files at once without explicit user confirmation — that's a sustained workload on whoever's CLI session runs it.
