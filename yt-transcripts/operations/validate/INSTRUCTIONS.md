# Skill: validate

**Purpose**: Walk the corpus and check every `.md` file conforms to the schema, path conventions, uniqueness, and timestamp requirements. Reports issues; doesn't fix them.

**Input**: None (operates on `/output/by-channel/`).

**Output**: A report to stdout (and optionally written to `/logs/validate-{date}.log`).

---

## How to run

Just invoke. No arguments. Read-only — never modifies files.

Mechanical work in `scripts/validate_corpus.py`. The skill invokes it and surfaces the report.

---

## Checks performed

For each `.md` file under `/output/by-channel/`:

1. **Frontmatter parses as YAML** (no malformed YAML, no missing `---` delimiters).
2. **All required fields present** per [`schemas/frontmatter.schema.md`](../../schemas/frontmatter.schema.md).
3. **Types match** (strings are strings, ints are ints, dates are valid `YYYY-MM-DD`).
4. **Enums valid**:
   - `transcript_source` ∈ {`manual_captions`, `auto_captions`, `whisper`, `none`}
   - `content_type` ∈ taxonomy.md enum (when set)
   - `audience_level` ∈ taxonomy.md enum (when set)
5. **`video_id` is globally unique** across the entire `/output` tree.
6. **Filename matches** `{channel_slug}_YYYY-MM-DD_{video_id}.md`.
7. **Filename date matches `publish_date`** in frontmatter.
8. **File lives in `output/by-channel/{channel_slug}/`** and `channel_slug` in path matches frontmatter `channel_slug`.
9. **If `transcript_has_timestamps: true`**: at least one `[HH:MM:SS]` marker present in transcript body.
10. **If `enriched: true`**: `enrichment_date`, `enrichment_version`, `summary` all non-null/non-empty.
11. **`tags_topic` equals `topics`** (legacy alias mirror).
12. **`topics_proposed` contains no items that are also in `topics`**.
13. **`key_claims[].timestamp`** (if present) matches at least one `[HH:MM:SS]` marker in the body.
14. **Controlled-vocab check**: every item in `topics` is present in `config/taxonomy.md` (warning, not error, if taxonomy.md is empty).

---

## Report format

Group findings by severity:

```
== ERRORS (must fix) ==
output/by-channel/foo/2024-03-15_abc123.md
  - filename date '2024-03-15' does not match frontmatter publish_date '2024-03-16'
  - missing required field: language

== WARNINGS (consider fixing) ==
output/by-channel/bar/2024-07-22_xyz789.md
  - topic 'mega-backdoor-roth' not in controlled vocab (taxonomy.md is empty)

== STATS ==
Total files: 142
Errors: 2 (in 1 file)
Warnings: 7
Validation result: FAIL
```

Exit code 0 if no errors (warnings ok); non-zero if any errors.

---

## What NOT to do

- Don't modify any file. Validation is read-only.
- Don't auto-fix issues. Surface them so a human (or another skill) makes the call.
- Don't validate files outside `/output/by-channel/`.

---

## When to run

- Before any major operation (full enrichment run, embedding export, sharing with team).
- After any manual edits to `.md` files.
- Periodically (e.g. weekly) as drift detection.
- As part of the test plan before declaring a milestone complete.
