# yt-transcripts-web — CLAUDE.md

This file documents how to work with this codebase.

## What This Is

An agent-facing static knowledge base for 1,313+ YouTube videos from 11 finance channels. Deployed to Vercel; every push triggers a rebuild.

Read the main [README.md](../README.md) first.

## Quick Facts

- **Source**: `../Miediai Scripts/yt-transcripts/output/index.csv` + `by-channel/**/*.md`
- **Build output**: `public/` (static files) + `generated/` (function bundles)
- **Build command**: `npm run build` (via `tsx scripts/build-kb.ts`)
- **Deploy**: Push to repo, Vercel auto-deploys on main
- **Endpoints**: 1,313 video markdown files + `/api/search` + `/api/videos` + static JSON catalogs

## Folder Structure

```
lib/           Shared types, search config
scripts/       Build script (build-kb.ts)
api/           Serverless functions (search.ts, videos.ts)
public/        Built output (gitignored, rebuilt on each deploy)
generated/     Function bundles (gitignored, deployed with api/)
```

## How to Change Things

### Add/update videos in the source corpus

Edit or add .md files in `../Miediai Scripts/yt-transcripts/output/by-channel/`, then run:

```bash
npm run build
```

The build is idempotent — run it as many times as you need.

### Change the search behavior

Edit `lib/kbConfig.ts` — specifically `SEARCH_OPTIONS` (field boosting) and the parseCSVRow helper.

Then rebuild. The search index is regenerated each time.

### Change the digest or channel rows

Same: edit `lib/kbConfig.ts` types (DigestRow, ChannelRow), rebuild.

### Add a new API endpoint

1. Create `api/newfeature.ts` exporting a Vercel request handler
2. The build script auto-bundles `generated/` files, so load digest/index/search-index inside the handler
3. Rebuild and deploy

### Change the video card format

Edit the markdown extraction logic in `scripts/build-kb.ts` — specifically where it writes `/public/videos/<slug>/<id>.md` vs `_full.md`.

Currently: summary cards exclude the `## Transcript` section. The `_full.md` includes everything.

## Known Issues & TODOs

- **Top topics not populated**: `channels.json` has empty `top_topics` arrays. The build script computes them but the current data has empty topic lists. Once the yt-transcripts corpus adopts controlled vocabulary (is promoting `topics_proposed` to `topics`), this will auto-populate.
- **No entity filtering**: The build includes `entities` (people, companies, tickers, concepts) in the full index, but there's no `/api/entities` endpoint yet. Good follow-up.
- **No chunking for embedding**: The `generated/` directory doesn't include a pre-chunked JSONL for vector embedding. That's Layer 3 work — depends on implementing `/scripts/export_chunks.py` in the source yt-transcripts/ repo first.

## Testing Locally

```bash
npm run build
ls public/videos/benfelixcsi/ | head -5
cat public/digest.json | jq '.[] | select(.channel_slug == "benfelixcsi") | {title, summary}' | head -2
```

## Deployment

```bash
# Preview
vercel

# Production (be careful!)
vercel --prod
```

Vercel auto-detects `vercel.json` and uses it for build command, output dir, function routing.

## Context for Future Work

When you open this repo in Claude Code:

1. You're working with a **static knowledge base** — all logic is at build time, not runtime. Changes require a rebuild + redeploy.
2. The **source truth** is `../Miediai Scripts/yt-transcripts/output/` — this repo only consumes it, never modifies it.
3. The **search index** (MiniSearch) is pre-built and serialized; it's bundled into the api functions at deploy time.
4. The **API functions** are cheap — they just load serialized data and filter/search. No database calls.
5. Metadata changes (summary, topics, entities) come from the source corpus enrichment, not from this layer.

## Files You'll Edit Most Often

- `scripts/build-kb.ts` — build logic
- `lib/kbConfig.ts` — types and search options
- `api/search.ts`, `api/videos.ts` — API behavior
