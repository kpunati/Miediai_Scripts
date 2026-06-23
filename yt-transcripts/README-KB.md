# YouTube Transcripts Knowledge Base

Agent-facing web knowledge base for 1,313+ YouTube videos from 11 finance/investing channels. Built for efficient LLM access with BM25 search, structured filtering, and summary cards.

## What This Is

A static Vercel deployment that makes your YouTube transcript corpus accessible to agents and LLMs in ~1-2KB per query instead of thousands. Endpoints for:
- **BM25 search** — keyword search across titles + summaries + topics
- **Structured filtering** — by channel, content type, audience level, topic
- **Video cards** — one markdown file per video with summary (no transcript) or full transcript
- **Agent onboarding** — `/llms.txt` with complete query patterns and schemas

## Quick Start

### Local build

```bash
npm install
npm run build
```

This reads from `../Miediai Scripts/yt-transcripts/output/index.csv` and generates:
- `public/` — static files (digest.json, channels.json, video markdown, llms.txt)
- `generated/` — search index + data bundles for API functions

### Deploy to Vercel

One-time setup:

```bash
# Log in to Vercel and link this repo
vercel

# Deploy (preview)
vercel

# Deploy to production
vercel --prod
```

Every push to main rebuilds the KB automatically.

## Architecture

- **Build script** (`scripts/build-kb.ts`) — reads the yt-transcripts corpus, slices into summary cards + full files, builds search index
- **API functions** (`api/search.ts`, `api/videos.ts`) — serverless endpoints for search and filtering
- **Static files** — 1,313 markdown files + digest/channels/index JSON + llms.txt

## Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/digest.json` | All 1,313 videos (~1.5MB), one row per video |
| GET | `/channels.json` | 11 channels with counts and date ranges |
| GET | `/api/search?q=index+funds&k=10` | BM25 search → top 10 results |
| GET | `/api/videos?channel=benfelixcsi&topic=behavioral-finance` | Structured filter |
| GET | `/videos/benfelixcsi/DQAr1DeDIro.md` | Video summary card (no transcript) |
| GET | `/videos/benfelixcsi/DQAr1DeDIro_full.md` | Full video with transcript |

See `/llms.txt` for complete documentation.

## File Size Reference

- `digest.json` — 1.5MB (1,313 rows × ~1.2KB each)
- `channels.json` — 2.6KB (11 channels)
- Video summary card — 4-8KB (frontmatter + summary + key takeaways + detailed notes, no transcript)
- Video full card — 50-150KB (includes transcript)
- Search index — 1.5MB (MiniSearch serialized)

## Query Pattern (Agent Perspective)

```
1. GET /channels.json  (2.6KB)  ← pick channel(s)
2. GET /api/search?q=behavioral+finance&k=10  (5-10KB)  ← find videos
3. GET /videos/benfelixcsi/K-U6eoICrYQ.md  (5KB)  ← read summary
4. (optional) GET /videos/benfelixcsi/K-U6eoICrYQ_full.md  (80KB)  ← read full transcript
```

Total: ~13KB for discovery, optional +80KB for deep read.

## Development

### Adding videos to the corpus

Push new video markdown files to `../Miediai Scripts/yt-transcripts/output/by-channel/` and rebuild:

```bash
npm run build
```

The build script is idempotent — running it multiple times produces the same output.

### Updating video metadata

Edit the `.md` file in the source corpus and rebuild. The build script reads frontmatter directly from source files.

### Regenerating search index

Just run the build again. The search index is regenerated from scratch each time.

## Vercel Configuration

- **Build command**: `tsx scripts/build-kb.ts`
- **Output directory**: `public/`
- **Node version**: 20.x (default)
- **Environment variables**: None required
- **Caching**: Static files get cache headers; API functions bundle generated/ files

See `vercel.json` for details.

## Monitoring

After deployment, check:

```bash
# Check digest endpoint
curl https://<your-url>/digest.json | jq '.[] | select(.channel_slug == "benfelixcsi")' | head -3

# Check search
curl "https://<your-url>/api/search?q=behavioral+finance&k=5" | jq '.results'

# Check filter
curl "https://<your-url>/api/videos?channel=benfelixcsi&k=3" | jq '.results'
```

## Roadmap

- [ ] Promote proposed topics to controlled vocabulary (consolidate topic synonyms)
- [ ] Add /api/entities endpoint to filter by people, companies, tickers mentioned
- [ ] Add /api/export endpoint for chunking/embedding (Layer 3 prep)
- [ ] Add webhook to auto-rebuild when yt-transcripts source updates

## Support

See `/llms.txt` for complete agent-facing documentation. See `../Miediai Scripts/yt-transcripts/` for source corpus schema and operations.
