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
  TopicRow,
  EntityRow,
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

      // Extract entities and claims from frontmatter
      const entityNames = new Set<string>();
      const concepts = new Set<string>();
      const keyClaims: Array<{ claim: string; timestamp: string; confidence: 'high' | 'medium' | 'low' }> = [];

      if (frontmatter.entities) {
        const ent = frontmatter.entities;
        if (ent.people) ent.people.forEach((p: any) => entityNames.add(p.name));
        if (ent.companies) ent.companies.forEach((c: any) => entityNames.add(c.name));
        if (ent.products) ent.products.forEach((p: any) => entityNames.add(p));
        if (ent.concepts) ent.concepts.forEach((c: any) => concepts.add(c));
      }

      if (frontmatter.key_claims && Array.isArray(frontmatter.key_claims)) {
        frontmatter.key_claims.forEach((kc: any) => {
          keyClaims.push({
            claim: kc.claim,
            timestamp: kc.timestamp || '',
            confidence: kc.confidence || 'medium',
          });
        });
      }

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
        key_claims: keyClaims,
        entity_names: Array.from(entityNames),
        concepts: Array.from(concepts),
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

  // Compute top topics per channel & build topic index
  const topicCounts = new Map<string, Map<string, number>>();
  const topicByChannel = new Map<string, Set<string>>();
  const topicEnrichedCounts = new Map<string, number>();

  videos.forEach((v) => {
    if (!topicCounts.has(v.digest.channel_slug)) {
      topicCounts.set(v.digest.channel_slug, new Map());
      topicByChannel.set(v.digest.channel_slug, new Set());
    }
    const counts = topicCounts.get(v.digest.channel_slug)!;
    const channels_set = topicByChannel.get(v.digest.channel_slug)!;
    v.digest.topics.forEach((t) => {
      counts.set(t, (counts.get(t) || 0) + 1);
      topicEnrichedCounts.set(t, (topicEnrichedCounts.get(t) || 0) + (v.digest.enriched ? 1 : 0));
      channels_set.add(v.digest.channel_slug);
    });
  });

  channels.forEach((ch) => {
    const counts = topicCounts.get(ch.channel_slug) || new Map();
    ch.top_topics = Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map((e) => e[0]);
  });

  // Build topics index
  const topicsIndex = new Map<string, TopicRow>();
  topicCounts.forEach((channelTopics, channel) => {
    channelTopics.forEach((count, topic) => {
      if (!topicsIndex.has(topic)) {
        topicsIndex.set(topic, {
          topic,
          count: 0,
          enriched_count: 0,
          channels: [],
        });
      }
      const row = topicsIndex.get(topic)!;
      row.count += count;
      row.enriched_count += topicEnrichedCounts.get(topic) || 0;
      if (!row.channels.includes(channel)) {
        row.channels.push(channel);
      }
    });
  });

  // Build entities index
  const entitiesIndex = new Map<string, EntityRow>();
  videos.forEach((v) => {
    v.digest.entity_names.forEach((name) => {
      if (!entitiesIndex.has(name)) {
        entitiesIndex.set(name, {
          name,
          type: 'concept',
          count: 0,
          channels: [],
        });
      }
      const row = entitiesIndex.get(name)!;
      row.count++;
      if (!row.channels.includes(v.digest.channel_slug)) {
        row.channels.push(v.digest.channel_slug);
      }
    });
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

  // Write topics.json
  await fs.writeFile(
    path.join(PUBLIC, 'topics.json'),
    JSON.stringify(Array.from(topicsIndex.values()), null, 2)
  );
  console.log(`✓ topics.json (${topicsIndex.size} topics)`);

  // Write entities.json
  await fs.writeFile(
    path.join(PUBLIC, 'entities.json'),
    JSON.stringify(Array.from(entitiesIndex.values()), null, 2)
  );
  console.log(`✓ entities.json (${entitiesIndex.size} entities)`);

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

  // Copy to generated for API functions
  await fs.writeFile(
    path.join(GENERATED, 'digest.json'),
    JSON.stringify(digest)
  );
  await fs.writeFile(
    path.join(GENERATED, 'channels.json'),
    JSON.stringify(Array.from(channels.values()))
  );
  await fs.writeFile(
    path.join(GENERATED, 'topics.json'),
    JSON.stringify(Array.from(topicsIndex.values()))
  );
  await fs.writeFile(
    path.join(GENERATED, 'entities.json'),
    JSON.stringify(Array.from(entitiesIndex.values()))
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
  const uniqueTopics = new Set<string>();
  digest.forEach((d) => d.topics.forEach((t) => uniqueTopics.add(t)));

  return `# YouTube Transcripts KB

A lean, agent-first knowledge base for ${totalVideos}+ YouTube videos from ${totalChannels} finance channels. **Topic-first architecture** — search by topics, entities, and claims, not just channels.

## Catalog Stats

- **Total videos**: ${totalVideos}
- **Channels**: ${totalChannels}
- **Enriched**: ${enrichedCount} (${Math.round((enrichedCount / totalVideos) * 100)}%)
- **Topics**: ${uniqueTopics.size} distinct tags
- **Coverage**: retirement planning, behavioral finance, investing, wealth management, financial advice

## Topic-First Query Flow

Instead of starting with channels, discover topics first:

1. **Discover topics**: \`GET /api/topics\` — returns all available topics with video counts
2. **Search by topic**: \`GET /api/videos?topic=behavioral-finance&k=10\` — get videos tagged with a specific topic
3. **Refine search**: Add filters like \`?audience_level=intermediate&content_type=educational\`
4. **Fetch summary**: \`GET /videos/<channel_slug>/<video_id>.md\` — summary card with key_claims (5KB)
5. **Full transcript**: \`GET /videos/<channel_slug>/<video_id>_full.md\` — only when you need the complete text

**OR** search by keyword:
- \`GET /api/search?q=private+credit&k=10\` — BM25 over titles + summaries + topics
- \`GET /api/entities?q=behavioral&k=10\` — search entities and concepts

## Endpoints

| Endpoint | Kind | Purpose |
|---|---|---|
| \`/digest.json\` | static | slim catalog, one row per video (~${Math.round(totalVideos * 0.05)}KB) |
| \`/topics.json\` | static | all topics with counts and channel coverage |
| \`/entities.json\` | static | all entities/concepts with counts |
| \`/channels.json\` | static | channel list with counts and top topics |
| \`/index.json\` | static | full field map with entities + key_claims |
| \`/api/topics\` | function | discover available topics; supports filtering |
| \`/api/entities?q=&type=\` | function | search entities/concepts by name or type |
| \`/api/search?q=&k=&offset=\` | function | BM25 keyword search → ranked hits with snippet |
| \`/api/videos?topic=&entity=&concept=&channel=&audience_level=&content_type=&q=&k=&offset=\` | function | structured filter by any dimension |
| \`/videos/<channel_slug>/<video_id>.md\` | static | summary card with key_claims (no transcript) |
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
- \`topics\`: Controlled-vocabulary topic tags (canonical; 0-6 items)
- \`topics_proposed\`: Proposed topics from enrichment (backup; not yet canonicalized)
- \`summary\`: 1-3 sentence enrichment summary
- \`url\`: Canonical YouTube watch URL
- \`key_claims\`: High-confidence factual claims with timestamps (from frontmatter)
- \`entity_names\`: Person/company/product names extracted from entities (for filtering)
- \`concepts\`: Concept tags from entity enrichment (for semantic search)
- \`path\`: URL path to summary card (/videos/<slug>/<id>.md)
- \`full_path\`: URL path to full file with transcript
- \`enriched\`: Boolean — true if summary/topics/entities have been added
- \`flags\`: Array like "whisper_review_needed", "unpunctuated_captions"

**TopicRow** (from /topics.json):
- \`topic\`: Topic slug (e.g., "behavioral-finance")
- \`count\`: Total videos tagged with this topic
- \`enriched_count\`: Videos with full enrichment
- \`channels\`: List of channels that cover this topic

**EntityRow** (from /entities.json):
- \`name\`: Entity name (person, company, product, or concept)
- \`type\`: "person" | "company" | "concept" | "product"
- \`count\`: Videos mentioning this entity
- \`channels\`: Channels that mention this entity

## Query Patterns

**Example: "What topics are available?"**
\`\`\`
GET /api/topics
→ [{topic: "behavioral-finance", count: 12, ...}, {topic: "retirement-planning", count: 8, ...}, ...]
\`\`\`

**Example: "Give me all intermediate-level videos on behavioral finance"**
\`\`\`
GET /api/videos?topic=behavioral-finance&audience_level=intermediate&k=10
\`\`\`

**Example: "Find videos mentioning 'Ben Felix' or discussing specific companies"**
\`\`\`
GET /api/entities?q=ben+felix&k=5
GET /api/videos?entity=Vanguard&k=10
\`\`\`

**Example: "Search for content on private credit"**
\`\`\`
GET /api/search?q=private+credit&k=5
→ fetch each hit's /videos/<slug>/<id>.md to see key_claims and full context
\`\`\`

**Example: "Find claims about fee structures across the KB"**
\`\`\`
GET /api/videos?q=fees&k=20  ← filters by keyword
→ /videos/<slug>/<id>.md includes key_claims with claim text + timestamp
\`\`\`

Then fetch full transcript only if you need the verbatim text:
\`\`\`
GET /videos/<slug>/<id>_full.md
\`\`\`

## No Hallucination Rule

Do not make up video counts, topics, entities, or claims. Verify against /digest.json, /topics.json, /entities.json first.

## Deploy

This is a static site generated from \`yt-transcripts/output/\`. Every push triggers a rebuild.

Base URL: (set by Vercel project)
`;
}

main().catch((e) => {
  console.error('Build failed:', e);
  process.exit(1);
});
