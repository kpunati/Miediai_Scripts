# Enrichment Output Schema (strict)

The exact shape the `enrich` skill must produce. This is the deterministic contract — independent of which LLM runs the enrichment.

## Frontmatter fields written by enrichment

```yaml
enriched: true                          # bool, required
enrichment_date: "2026-05-15"           # date (YYYY-MM-DD), required, today's date UTC
enrichment_version: 1                   # int, required, current = 1

summary: "1-3 sentence neutral factual summary."   # string, required, 50-500 chars
topics: ["retirement-planning", "tax-strategy"]    # list[string], 0-6 items, controlled vocab from config/taxonomy.md
topics_proposed: ["mega-backdoor-roth"]            # list[string], 0-6 items, lowercase-hyphenated, not yet in controlled vocab

entities:
  people:
    - name: "Jane Doe"                  # string, required
      role: "CFP at XYZ Wealth"         # string, optional
  companies:
    - name: "Vanguard"                  # string, required
      ticker: null                      # string|null, optional
  tickers:
    - "VTI"                             # bare ticker strings
  funds:
    - name: "Vanguard Total Stock Market ETF"
      ticker: "VTI"                     # string|null
  products:
    - "M1 Finance"                      # plain strings
  concepts:
    - "dollar-cost-averaging"

content_type: "educational"             # enum, required, one of: educational|opinion|news|interview|analysis|case-study|other
audience_level: "intermediate"          # enum, required, one of: beginner|intermediate|advanced|mixed

key_claims:                             # list[object], 0-5 items
  - claim: "Index funds outperform actively managed funds 80% of the time over 20 years"
    timestamp: "00:04:12"               # string (HH:MM:SS), required, must match a marker in the transcript
    confidence: "medium"                # enum, required, one of: high|medium|low
    flagged: false                      # bool, required

tags_topic: ["retirement-planning", "tax-strategy"]   # MIRROR of topics — must be identical

flags: ["whisper_review_needed"]        # list[string], may include new entries appended by enrichment
```

## Body sections written by enrichment

In addition to populating the frontmatter, enrichment INSERTS three required sections into the body, in this order, BEFORE the existing `## Transcript` section:

```markdown
## Summary

<2-4 sentence readable summary>

## Key Takeaways

- Point 1
- Point 2
- ...
- (4-7 bullets total)

## Detailed Notes

### Subheading [HH:MM:SS]
<1-4 sentence notes>

### Next subheading [HH:MM:SS]
<more notes>

### ...
```

See [INSTRUCTIONS.md](./INSTRUCTIONS.md) → "Body sections" for content rules per section.

## Validation rules

A file is rejected (and `flags: [enrichment_failed]` set) if any of these fail:

1. `summary` is empty, under 50 chars, or over 500 chars.
2. `topics + topics_proposed` together exceed 8 items.
3. An item in `topics` is not present in `config/taxonomy.md` (when taxonomy.md has content).
4. `entities` is missing any of the six required keys (each may be an empty list).
5. `content_type` or `audience_level` is not in their allowed enum.
6. Any `key_claims[].timestamp` does not match an `[HH:MM:SS]` marker in the transcript body.
7. `tags_topic` does not equal `topics` exactly.
8. The original `description` (frontmatter), `## Transcript` section, or any identifier field was modified.
9. When `enriched: true`, body is missing any of: `## Summary`, `## Key Takeaways`, `## Detailed Notes`.
10. `## Detailed Notes` has zero `### ` subsections.
11. Any `### Subheading [HH:MM:SS]` timestamp in Detailed Notes does not match a marker in the transcript.

## Defaults / empty cases

- If no notable entities of a type: empty list `[]`, not omitted.
- If no key_claims worth extracting: empty list `[]`.
- If taxonomy.md is empty: `topics: []`, all topics go into `topics_proposed`.
- `enrichment_version: 1` until these instructions or the schema materially change.
