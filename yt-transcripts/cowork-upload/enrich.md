# Skill: enrich

**Purpose**: Walk transcript files where `enriched: false` and populate the reserved enrichment fields in frontmatter, using the model-agnostic schema and rules below. Distributed: anyone in the org with the repo and any capable LLM CLI runs this.

**Input**: Files under `/output/by-channel/**/*.md` where `enriched: false`.

**Output**: Same files, with reserved enrichment fields populated and `enriched: true`. Original transcript text is never modified.

---

## How to run

The agent (you) is invoked by the user with one of these intents:

- "Enrich the next N files." → Process N files where `enriched: false`, oldest first.
- "Enrich {channel-slug}." → Process all unenriched files in `output/by-channel/{slug}/`.
- "Enrich video {video_id}." → Process the one matching file.
- "Enrich everything." → Process all `enriched: false` files until done. **Confirm with user before starting** if the count is over 20 (rate of work and budget on their CLI tier matters).

Default if intent is unclear: process the next 5 unenriched files and report back.

### Per-file workflow

For each target file:

1. **Read** the full file (frontmatter + body).
2. **Skip** if `enriched: true` already.
3. **Generate** the enrichment output per the rules below and the strict schema in [`output_schema.md`](./output_schema.md).
4. **Validate** the output against the schema *before* writing back. Specifically:
   - **Verify every `key_claims[].timestamp` exists as a literal `[HH:MM:SS]` marker in the transcript body.** Grep the body for each timestamp you produced. If it's not there, you hallucinated it — find the actual nearest preceding marker by re-reading the transcript and fix the value. This is the single most common enrichment mistake; do not skip this step. (The applier in step 6 will auto-snap stragglers, but get them right yourself first.)
   - Check `summary` length is between 50 and 500 chars.
   - Confirm `entities` has all six required keys (`people`, `companies`, `tickers`, `funds`, `products`, `concepts`), each as a list (empty `[]` is fine).
   - Confirm `content_type` and `audience_level` are in the allowed enum.
   - Confirm `tags_topic` exactly equals `topics`.
   - Confirm `topics + topics_proposed` together have ≤ 8 items.

   If invalid, fix and retry once. If still invalid, flag the file (`flags: [enrichment_failed]`) and move on — don't write garbage.
5. **Assemble** the enrichment payload as JSON matching the shape documented at the top of [`scripts/apply_enrichment.py`](../../scripts/apply_enrichment.py) (summary, topics, topics_proposed, entities, content_type, audience_level, key_claims, flags_to_add, body{summary, key_takeaways, detailed_notes}).
6. **Apply via the canonical script** — do not write ad-hoc regex substitutions:
   ```bash
   python scripts/apply_enrichment.py --json /tmp/payload.json
   # or pipe: cat payload.json | python scripts/apply_enrichment.py --stdin
   ```
   The applier bakes in the fixes we learned the hard way and **must** be your write path:
   - Auto-trims oversize summaries at the last sentence boundary (>500 chars → snapped before 470).
   - Snaps every `key_claims[]` and `detailed_notes[]` timestamp to the nearest preceding marker actually present in the transcript.
   - Dedupes/lowercases topics, drops overlap, caps `topics + topics_proposed` at 8.
   - Mirrors `topics` into `tags_topic`.
   - Sets `enriched: true`, `enrichment_date` (today UTC), `enrichment_version: 1`.
   - Appends to `flags` (never replaces).
   - Inserts the three required body sections before `## Transcript`; preserves the title, header block, and original `## Transcript` byte-for-byte.

   Use `--dry-run` first if you're unsure — it validates and reports auto-fixes without writing.
7. **Append** an optional `## Enrichment Notes` section at the very end of the body only if the structured fields can't capture something material (rare — most files don't need this).
8. **Log** to the chat: filename, summary (one line), topic count, entity count, any auto-fixes the applier reported, time taken.

After the batch — **always** run:
```bash
python scripts/post_enrich.py
```
This wraps `validate_corpus` → `build_index` → `corpus_status` so the index can't drift behind the corpus. If `validate_corpus` fails, the index is **not** rebuilt; fix errors and re-run.

---

## Generation rules (per field)

### `summary` (string, 1–3 sentences)

A neutral, factual summary of what the video covers and what positions/claims it makes. Written for someone deciding whether to read the full transcript. No marketing language. No first person.

**Good**: *"Argues that small business owners should fund a SEP-IRA before a 401(k) due to higher contribution limits and lower admin overhead. Walks through 2024 contribution math and contrasts with a solo 401(k) for self-employed individuals."*

**Bad**: *"In this engaging video, the creator dives into retirement planning options."* (no information content, fluffy)

**Bad**: *"I think this is about retirement."* (first person, hedging)

### `topics` (list of strings, 2–6 items)

Topics from the controlled vocabulary in [`config/taxonomy.md`](../../config/taxonomy.md). If a topic clearly matches a controlled term, use it. Otherwise put the proposed topic in `topics_proposed`.

If `config/taxonomy.md` is empty or sparse (early in the project's life), put all topics in `topics_proposed` and leave `topics` empty. The vocabulary will be promoted from `topics_proposed` over time.

### `topics_proposed` (list of strings, 0–6 items)

Topics that don't yet have a controlled-vocab term. Use specific, lowercase, hyphenated forms (e.g. `mega-backdoor-roth`, not `Mega Backdoor Roth Strategy`).

### `entities` (structured object)

Extract only entities clearly mentioned and material to the video's content. Skip passing references.

- `people`: `{name, role?}`. Role is optional — fill if the video establishes it (e.g. `"CEO of Acme"`).
- `companies`: `{name, ticker?}`. Ticker only if the video states it or it's a well-known public company.
- `tickers`: bare stock/fund tickers (e.g. `"VTI"`, `"AAPL"`). Cross-reference with `companies` and `funds` entries.
- `funds`: `{name, ticker?}`. Mutual funds, ETFs, hedge funds named in the video.
- `products`: named products or services (e.g. `"QuickBooks"`, `"M1 Finance"`).
- `concepts`: financial / business / marketing concepts (e.g. `"dollar-cost-averaging"`, `"customer-acquisition-cost"`).

**Rule**: if the transcript source is `whisper` or `auto_captions`, treat tickers and dollar amounts as low-confidence (this is the known weak spot per [`PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)). When extracting tickers from those sources, also add `whisper_review_needed` to the file's `flags` (if not already present).

### `content_type` (enum)

Pick exactly one from the list in [`config/taxonomy.md`](../../config/taxonomy.md). If genuinely uncertain between two, prefer the more specific one.

### `audience_level` (enum)

Pick exactly one. Use `mixed` only when the video genuinely spans multiple levels (e.g. opens with basics, ends with advanced detail).

### `key_claims` (list of objects, 0–5 items)

Notable, fact-checkable claims the video makes. Skip the obvious or generic. Each claim:

```yaml
- claim: "Index funds outperform actively managed funds 80% of the time over 20 years"
  timestamp: "00:04:12"     # nearest preceding [HH:MM:SS] marker in transcript
  confidence: "medium"      # high | medium | low — your confidence the claim is accurately captured
  flagged: false            # true if claim contains a number/ticker likely mistranscribed
```

Set `flagged: true` for claims that involve specific dollar amounts, percentages, tickers, or fund names **when the transcript source is `whisper` or `auto_captions`** — those are the high-risk mistranscription cases.

### `flags`

Add (don't replace) entries to `flags` as appropriate:
- `whisper_review_needed` if any extracted ticker/dollar amount/specific number came from `whisper` or `auto_captions` source.
- `enrichment_failed` if validation failed twice and you bailed.
- Other ad-hoc flags as you see fit, but stay consistent with anything already in use.

---

## Body sections (required when enriched)

After enrichment, the body of the `.md` file must contain these sections in this order, BEFORE the `## Transcript` section:

### `## Summary` (one short paragraph)

A 2–4 sentence readable summary of the video. More substantive than the terse frontmatter `summary` field — written for a reader deciding whether to invest time in the video. Mention specific positions or claims if they're central to the video's argument. No marketing language. No first person.

### `## Key Takeaways` (4–7 bullets)

The main points or things a reader should walk away with. Each bullet is one sentence (occasionally two). Action-oriented where applicable ("Index funds typically outperform actively managed funds because…"); descriptive where not ("Defines dividend yield as the dividend amount relative to share price").

Don't repeat the summary. Don't list every minor point. Pick what's most useful for someone scanning to decide whether the video applies to their situation.

### `## Detailed Notes` (section-by-section walkthrough)

Organized notes structured by topic. Each major topic becomes a `### Subheading [HH:MM:SS]` subsection, where the timestamp is the nearest preceding marker in the transcript. Each subsection has 1–4 sentences of notes summarizing what's said in that part of the video.

This is the most labor-intensive section but the most useful for someone deciding whether to watch — they can scan section headings, see what's covered, and dive into the transcript at the right timestamp if they want detail.

Aim for 4–8 subsections for a typical 5–20 minute video. Use the transcript paragraphs (`[HH:MM:SS]` markers) as natural anchor points but don't slavishly mirror them — group related paragraphs into one subsection when appropriate.

Format example:

```markdown
## Detailed Notes

### Why compounding favors early starters [00:00:04]
Walks through a 30-year hypothetical: investor A puts in $1K/yr for 15 years then stops; investor B starts 15 years later but puts in $3K/yr. Despite investing 3x more, B ends up ~$37K behind A because A's earlier dollars had more time to compound.

### The case against market timing [00:02:08]
Missing just the 5 best market days over 20 years would have cost ~1/3 of portfolio value. Missing the top 25 best days leaves you barely above where you started. Many of those best days came within weeks of market crises.

### Diversification across asset classes [00:05:18]
…
```

---

## What enrichment must NOT do

- Modify the description or transcript body text.
- Change identifier fields (`video_id`, `url`, `channel_id`, etc.).
- Delete or rename any frontmatter field.
- Move or rename the file.
- Update `view_count_at_ingest` — that field captures a moment in time.
- Add fields not in the schema. If you think a new field is warranted, leave a note in `## Enrichment Notes` flagging it for the human to consider.

---

## Cross-CLI portability

These instructions are deliberately written in plain prose — they should produce comparable output whether run via Claude Code, Codex CLI, Gemini CLI, or any other capable LLM CLI. The strict output schema in [`output_schema.md`](./output_schema.md) is the deterministic contract.

If your CLI has shortcuts that make the workflow faster (file globbing, batch operations), use them — but don't deviate from the schema or rules above.

---

## When you're done

Report back to the user:
- Number of files processed.
- Any files flagged or failed.
- Any auto-fixes the applier reported (summaries trimmed, timestamps snapped, topics dropped to fit ≤8 cap) — these are not errors but worth surfacing.
- Confirm you ran `python scripts/post_enrich.py` and that validation passed + the index was rebuilt.
