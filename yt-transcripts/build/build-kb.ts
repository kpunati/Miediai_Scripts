/*
 * build-kb.ts — generates the agent-facing knowledge base from the
 * yt-transcripts corpus. Runs at Vercel build time.
 *
 * Reads: ./output/index.csv, ./output/by-channel/
 * Writes: public/ (static files), generated/ (bundled into api functions)
 */

import { promises as fs } from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import matter from 'gray-matter';
import MiniSearch from 'minisearch';
import {
  DigestRow,
  ChannelRow,
  IndexRow,
  SEARCH_OPTIONS,
  parseCSVRow,
  SearchIndexEntry,
} from '../lib/kbConfig';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');
const PUBLIC = path.join(REPO_ROOT, 'public');
const GENERATED = path.join(REPO_ROOT, 'generated');
const TRANSCRIPTS_OUTPUT = path.join(REPO_ROOT, 'output');
const INDEX_CSV = path.join(TRANSCRIPTS_OUTPUT, 'index.csv');

interface VideoData {
  digest: DigestRow;
  full: IndexRow;
  body: string;
}

async function main() {
  console.log('Starting KB build...');

  // Clean and create directories
  await fs.rm(PUBLIC, { recursive: true, force: true });
  await fs.rm(GENERATED, { recursive: true, force: true });
  await fs.mkdir(path.join(PUBLIC, 'videos'), { recursive: true });
  await fs.mkdir(GENERATED, { recursive: true });

  // Read index.csv
  const indexContent = await fs.readFile(INDEX_CSV, 'utf-8');
  const lines = indexContent.trim().split('\n');
  const headers = parseCSVLine(lines[0]);

  const videos: VideoData[] = [];
  const channels = new Map<string, ChannelRow>();
  const searchIndex = new MiniSearch<SearchIndexEntry>(SEARCH_OPTIONS);

  let processed = 0;
  let skipped = 0;

  for (let i = 1; i < lines.length; i++) {
    try {
      const csvRow = parseCSVRow(lines[i], headers);
      if (!csvRow) {
        skipped++;
        continue;
      }

      const relpath = (lines[i].split(',').pop() || '').trim();
      if (!relpath) {
        skipped++;
        continue;
      }

      // relpath includes "output/" prefix from CSV; strip it since TRANSCRIPTS_OUTPUT already points to output/
      const cleanRelpath = relpath.startsWith('output/')
        ? relpath.substring('output/'.length)
        : relpath;
      const filePath = path.join(TRANSCRIPTS_OUTPUT, cleanRelpath);
      let fileContent: string;

      try {
        fileContent = await fs.readFile(filePath, 'utf-8');
      } catch (e) {
        console.warn(`[SKIP] File not found: ${relpath}`);
        skipped++;
        continue;
      }

      const { data: frontmatter } = matter(fileContent);

      // Build DigestRow
      const digest: DigestRow = {
        video_id: csvRow.video_id!,
        channel_slug: csvRow.channel_slug!,
        channel_name: csvRow.channel_name!,
        title: csvRow.title!,
        publish_date: csvRow.publish_date!,
        duration_seconds: csvRow.duration_seconds!,
        view_count_at_ingest: csvRow.view_count_at_ingest!,
        content_type: csvRow.content_type || 'other',
        audience_level: csvRow.audience_level || 'mixed',
        topics: csvRow.topics || [],
        topics_proposed: csvRow.topics_proposed || [],
        summary: csvRow.summary || '',
        url: csvRow.url!,
        path: `/videos/${csvRow.channel_slug!}/${csvRow.video_id!}.md`,
        full_path: `/videos/${csvRow.channel_slug!}/${csvRow.video_id!}_full.md`,
        enriched: csvRow.enriched || false,
        flags: csvRow.flags || [],
      };

      // Build IndexRow with additional fields
      const full: IndexRow = {
        ...digest,
        entities: frontmatter.entities || {
          people: [],
          companies: [],
          tickers: [],
          funds: [],
          products: [],
          concepts: [],
        },
        key_claims: frontmatter.key_claims || [],
      };

      videos.push({ digest, full, body: fileContent });

      // Add to search index
      searchIndex.add({
        id: `${csvRow.video_id!}`,
        video_id: csvRow.video_id!,
        channel_slug: csvRow.channel_slug!,
        channel_name: csvRow.channel_name!,
        title: csvRow.title!,
        summary: csvRow.summary || '',
        topics_str: (csvRow.topics || []).join(' '),
        publish_date: csvRow.publish_date!,
      });

      // Track channels
      const channelSlug = csvRow.channel_slug!;
      if (!channels.has(channelSlug)) {
        channels.set(channelSlug, {
          channel_slug: channelSlug,
          channel_name: csvRow.channel_name!,
          count: 0,
          enriched_count: 0,
          date_range: { earliest: csvRow.publish_date!, latest: csvRow.publish_date! },
          top_topics: [],
        });
      }

      const ch = channels.get(channelSlug)!;
      ch.count++;
      if (csvRow.enriched) ch.enriched_count++;
      if (csvRow.publish_date! < ch.date_range.earliest)
        ch.date_range.earliest = csvRow.publish_date!;
      if (csvRow.publish_date! > ch.date_range.latest)
        ch.date_range.latest = csvRow.publish_date!;

      processed++;
    } catch (e) {
      console.error(`[ERROR] Row ${i}:`, e);
      skipped++;
    }
  }

  console.log(
    `Processed ${processed} videos, skipped ${skipped}, total channels: ${channels.size}`
  );

  // Compute top topics per channel
  const topicCounts = new Map<string, Map<string, number>>();
  videos.forEach((v) => {
    if (!topicCounts.has(v.digest.channel_slug)) {
      topicCounts.set(v.digest.channel_slug, new Map());
    }
    const counts = topicCounts.get(v.digest.channel_slug)!;
    v.digest.topics.forEach((t) => {
      counts.set(t, (counts.get(t) || 0) + 1);
    });
  });

  channels.forEach((ch) => {
    const counts = topicCounts.get(ch.channel_slug) || new Map();
    ch.top_topics = Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map((e) => e[0]);
  });

  // Write digest.json
  const digest = videos.map((v) => v.digest);
  await fs.writeFile(
    path.join(PUBLIC, 'digest.json'),
    JSON.stringify(digest, null, 2)
  );
  console.log(`✓ digest.json (${digest.length} videos)`);

  // Write channels.json
  await fs.writeFile(
    path.join(PUBLIC, 'channels.json'),
    JSON.stringify(Array.from(channels.values()), null, 2)
  );
  console.log(`✓ channels.json`);

  // Write index.json
  const index = videos.map((v) => v.full);
  await fs.writeFile(
    path.join(PUBLIC, 'index.json'),
    JSON.stringify(index, null, 2)
  );
  console.log(`✓ index.json`);

  // Write individual video files
  for (const video of videos) {
    const d = video.digest;
    const dir = path.join(PUBLIC, 'videos', d.channel_slug);
    await fs.mkdir(dir, { recursive: true });

    // Summary card (no transcript)
    const cardContent = video.body.substring(
      0,
      video.body.indexOf('\n## Transcript')
    );
    await fs.writeFile(path.join(dir, `${d.video_id}.md`), cardContent);

    // Full file (with transcript)
    await fs.writeFile(path.join(dir, `${d.video_id}_full.md`), video.body);
  }
  console.log(`✓ Video markdown files`);

  // Write search index
  await fs.writeFile(
    path.join(GENERATED, 'search-index.json'),
    JSON.stringify(searchIndex.toJSON())
  );
  console.log(`✓ search-index.json`);

  // Copy digest to generated for api/videos.ts
  await fs.writeFile(
    path.join(GENERATED, 'digest.json'),
    JSON.stringify(digest)
  );
  await fs.writeFile(
    path.join(GENERATED, 'channels.json'),
    JSON.stringify(Array.from(channels.values()))
  );

  // Write llms.txt
  const llmsTxt = buildLlmsTxt(digest, channels);
  await fs.writeFile(path.join(PUBLIC, 'llms.txt'), llmsTxt);
  console.log(`✓ llms.txt`);

  // Write robots.txt
  await fs.writeFile(path.join(PUBLIC, 'robots.txt'), 'User-agent: *\nDisallow: /');
  console.log(`✓ robots.txt`);

  console.log('\n✅ KB build complete!');
}

function parseCSVLine(line: string): string[] {
  const result: string[] = [];
  let current = '';
  let insideQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];

    if (char === '"') {
      insideQuotes = !insideQuotes;
    } else if (char === ',' && !insideQuotes) {
      result.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }

  result.push(current.trim());
  return result;
}

function buildLlmsTxt(
  digest: DigestRow[],
  channels: Map<string, ChannelRow>
): string {
  const totalVideos = digest.length;
  const totalChannels = channels.size;
  const enrichedCount = digest.filter((d) => d.enriched).length;

  return `# YouTube Transcripts KB

A lean, agent-first knowledge base for 1,313+ YouTube videos from 11 finance channels.

## Catalog Stats

- **Total videos**: ${totalVideos}
- **Channels**: ${totalChannels}
- **Enriched**: ${enrichedCount} (${Math.round((enrichedCount / totalVideos) * 100)}%)
- **Coverage**: retirement planning, behavioral finance, investing, wealth management, financial advice

## How an Agent Uses It (token-efficient flow)

1. \`GET /channels.json\` — read once (~5KB): list of 11 channels with counts and date ranges.
2. \`GET /api/search?q=<terms>&k=10\` — BM25 search by keyword over titles + summaries + topics → ranked hits with snippet.
   OR \`GET /api/videos?channel=benfelixcsi&topic=behavioral-finance&k=20\` — structured filter.
3. \`GET /videos/<channel_slug>/<video_id>.md\` — fetch summary card (frontmatter + summary + key takeaways + detailed notes, NO transcript). Under 5KB per video.
4. \`GET /videos/<channel_slug>/<video_id>_full.md\` — full file including transcript (only when you need the complete transcript text).

≈ 1-2KB per question for filtering, 5KB for a summary card, 50-100KB for a full transcript.

## Endpoints

| Endpoint | Kind | Purpose |
|---|---|---|
| \`/digest.json\` | static | slim catalog, one row per video (~${Math.round(totalVideos * 0.05)}KB) |
| \`/channels.json\` | static | 11-row channel list with counts and topic summaries |
| \`/index.json\` | static | full field map with entities + key_claims |
| \`/api/search?q=&k=&offset=\` | function | BM25 keyword search → ranked hits with snippet |
| \`/api/videos?channel=&topic=&content_type=&audience_level=&q=&k=&offset=\` | function | structured filter |
| \`/videos/<channel_slug>/<video_id>.md\` | static | summary card (no transcript) |
| \`/videos/<channel_slug>/<video_id>_full.md\` | static | full file with transcript |
| \`/llms.txt\` | static | this file |

## Field Glossary

**DigestRow** (one per video):
- \`video_id\`: YouTube 11-char ID
- \`channel_slug\`, \`channel_name\`: Channel identifier and display name
- \`title\`: Video title
- \`publish_date\`: YYYY-MM-DD
- \`duration_seconds\`: Total video length
- \`view_count_at_ingest\`: Views at time of catalog ingest
- \`content_type\`: educational, opinion, interview, analysis, case-study, news, other
- \`audience_level\`: beginner, intermediate, advanced, mixed
- \`topics\`: Controlled-vocabulary topic tags (0-6 items)
- \`topics_proposed\`: Proposed topics from enrichment (0-6 items, not yet canonicalized)
- \`summary\`: 1-3 sentence enrichment summary
- \`url\`: Canonical YouTube watch URL
- \`path\`: URL path to summary card (/videos/<slug>/<id>.md)
- \`full_path\`: URL path to full file with transcript
- \`enriched\`: Boolean — true if summary/topics/entities have been added
- \`flags\`: Array of flags like "whisper_review_needed", "unpunctuated_captions"

**Markdown files** (per-video):
\`\`\`yaml
---
# Frontmatter block (YAML) — all fields above
video_id: "DQAr1DeDIro"
...
---

## Summary
(1-3 sentence factual summary from enrichment)

## Key Takeaways
- Bullet 1
- Bullet 2

## Detailed Notes
### Section [HH:MM:SS]
Notes per section of the video

## Transcript  ← ONLY in _full.md
[00:00:00] Transcript text...
[00:01:30] ...
\`\`\`

## Query Patterns

**Example: "Find all intermediate-level retirement planning content from Ben Felix"**
\`\`\`
GET /api/videos?channel=benfelixcsi&audience_level=intermediate&topic=retirement-planning&k=10
\`\`\`

**Example: "Find videos about behavioral finance across all channels"**
\`\`\`
GET /api/search?q=behavioral+finance&k=10
\`\`\`

**Example: "Search for content on option trading"**
\`\`\`
GET /api/search?q=options+trading&k=5
\`\`\`

Then for each hit, fetch the summary card to extract key_claims and topics without loading the transcript:
\`\`\`
GET /videos/benfelixcsi/K-U6eoICrYQ.md
\`\`\`

Only fetch the _full.md if you need the verbatim transcript text.

## No Hallucination Rule

Do not make up video counts, channel lists, or topic tags. Verify all facts against /digest.json and /channels.json first.

## Deploy

This is a static site generated from \`yt-transcripts/output/\`. Every push to the source triggers a rebuild.

Base URL: (set by Vercel project)
`;
}

main().catch((e) => {
  console.error('Build failed:', e);
  process.exit(1);
});
