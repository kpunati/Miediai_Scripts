import { VercelRequest, VercelResponse } from '@vercel/node';
import MiniSearch from 'minisearch';
import { readFileSync } from 'fs';
import { resolve } from 'path';
import { SearchIndexEntry, SEARCH_OPTIONS } from '../lib/kbConfig';

let searchIndex: MiniSearch<SearchIndexEntry> | null = null;

function loadSearchIndex(): MiniSearch<SearchIndexEntry> {
  if (searchIndex) return searchIndex;

  const indexPath = resolve(__dirname, '../generated/search-index.json');
  const indexData = readFileSync(indexPath, 'utf-8');
  searchIndex = MiniSearch.loadJSON(
    indexData,
    SEARCH_OPTIONS as Parameters<typeof MiniSearch.loadJSON>[1]
  );
  return searchIndex;
}

export default async (req: VercelRequest, res: VercelResponse) => {
  res.setHeader('Cache-Control', 'public, max-age=60, s-maxage=3600');
  res.setHeader('Content-Type', 'application/json');

  const { q, k = '10', offset = '0' } = req.query;

  if (!q || typeof q !== 'string' || q.trim().length === 0) {
    return res
      .status(400)
      .json({ error: 'Missing or empty query parameter: q' });
  }

  if (typeof k !== 'string' || typeof offset !== 'string') {
    return res.status(400).json({ error: 'Invalid k or offset parameter' });
  }

  const limit = Math.min(Math.max(parseInt(k, 10) || 10, 1), 100);
  const page = Math.max(parseInt(offset, 10) || 0, 0);

  try {
    const index = loadSearchIndex();
    const allResults = index.search(q.trim(), {
      boost: { title: 3, topics_str: 2.5, summary: 2, channel_name: 1 },
      fuzzy: 0.2,
    });

    const total = allResults.length;
    const start = page * limit;
    const results = allResults.slice(start, start + limit);

    return res.json({
      query: q,
      total,
      limit,
      offset: page,
      results: results.map((r) => ({
        video_id: r.video_id,
        channel_slug: r.channel_slug,
        channel_name: r.channel_name,
        title: r.title,
        summary: truncate(r.summary, 150),
        publish_date: r.publish_date,
        url: `https://youtube.com/watch?v=${r.video_id}`,
        path: `/videos/${r.channel_slug}/${r.video_id}.md`,
        score: r.score,
      })),
    });
  } catch (e) {
    console.error('Search error:', e);
    return res.status(500).json({ error: 'Search failed' });
  }
};

function truncate(text: string, maxLength: number): string {
  return text.length > maxLength ? text.substring(0, maxLength) + '…' : text;
}
