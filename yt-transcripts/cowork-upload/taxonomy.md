# Taxonomy — Controlled Vocabulary

This file defines the controlled vocabulary for the `tags_topic` and `topics` frontmatter fields. Enrichment uses these terms to keep the catalog filterable.

## Status

**Empty / growing organically.** Don't pre-optimize. Add terms here as the enrichment runs surface common themes. Aim for ~30–80 terms total when mature — small enough to be useful, big enough to cover the domain.

## How to add a term

1. Run a few enrichments without controlled vocab — let the LLM propose `topics` freely (open list).
2. After 20–50 enriched files, review the proposed topics. Cluster near-duplicates (e.g. "401k", "401(k)", "retirement plans" → pick one canonical form).
3. Add the canonical form to the appropriate section below.
4. From then on, enrichment is instructed to map proposed topics to this controlled list, falling back to `topics_proposed` (uncontrolled) for anything that doesn't map yet.

## Domain top-level categories

(populate during pilot)

### Finance — personal
<!-- e.g. retirement-planning, tax-strategy, budgeting, debt-management -->

### Finance — investing
<!-- e.g. equities, fixed-income, etfs, mutual-funds, alternatives -->

### Finance — business
<!-- e.g. small-business-finance, business-credit, cash-flow -->

### Management
<!-- e.g. leadership, team-building, hiring, performance-management -->

### Marketing
<!-- e.g. content-marketing, paid-acquisition, brand-strategy, seo -->

## Content type (also controlled)

The enrichment `content_type` field uses this fixed list:
- `educational` — primarily teaching a concept
- `opinion` — commentary or perspective
- `news` — reaction to a current event
- `interview` — guest-format conversation
- `analysis` — deep-dive on a specific situation or company
- `case-study` — walkthrough of a real example
- `other` — fall back when nothing else fits

## Audience level (also controlled)

- `beginner` — assumes no prior knowledge
- `intermediate` — assumes familiarity with the basics
- `advanced` — assumes deep domain knowledge
- `mixed` — accessible to multiple levels
