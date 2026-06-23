import { VercelRequest, VercelResponse } from '@vercel/node';
import { DigestRow } from '../lib/kbConfig';

let digestData: DigestRow[] | null = null;

async function loadDigest(): Promise<DigestRow[]> {
  if (digestData) return digestData;

  const data = await import('../generated/digest.json', {
    assert: { type: 'json' },
  });
  digestData = data.default;
  return digestData;
}

export default async (req: VercelRequest, res: VercelResponse) => {
  res.setHeader('Cache-Control', 'public, max-age=60, s-maxage=3600');
  res.setHeader('Content-Type', 'application/json');

  const {
    channel,
    content_type: contentType,
    audience_level: audienceLevel,
    topic,
    q,
    k = '20',
    offset = '0',
  } = req.query;

  const limit = Math.min(Math.max(parseInt(k as string, 10) || 20, 1), 100);
  const page = Math.max(parseInt(offset as string, 10) || 0, 0);

  try {
    let digest = await loadDigest();

    // Apply filters
    if (channel && typeof channel === 'string') {
      digest = digest.filter((d) => d.channel_slug === channel);
    }

    if (contentType && typeof contentType === 'string') {
      digest = digest.filter((d) => d.content_type === contentType);
    }

    if (audienceLevel && typeof audienceLevel === 'string') {
      digest = digest.filter((d) => d.audience_level === audienceLevel);
    }

    if (topic && typeof topic === 'string') {
      const topicLower = topic.toLowerCase();
      digest = digest.filter((d) =>
        d.topics.some((t) => t.toLowerCase().includes(topicLower)) ||
        d.topics_proposed.some((t) => t.toLowerCase().includes(topicLower))
      );
    }

    if (q && typeof q === 'string' && q.trim().length > 0) {
      const queryLower = q.toLowerCase();
      digest = digest.filter(
        (d) =>
          d.title.toLowerCase().includes(queryLower) ||
          d.summary.toLowerCase().includes(queryLower)
      );
    }

    // Sort by publish date descending
    digest.sort(
      (a, b) =>
        new Date(b.publish_date).getTime() -
        new Date(a.publish_date).getTime()
    );

    const total = digest.length;
    const start = page * limit;
    const results = digest.slice(start, start + limit);

    return res.json({
      filters: {
        channel: channel || null,
        content_type: contentType || null,
        audience_level: audienceLevel || null,
        topic: topic || null,
        q: q || null,
      },
      total,
      limit,
      offset: page,
      results: results.map((d) => ({
        video_id: d.video_id,
        channel_slug: d.channel_slug,
        channel_name: d.channel_name,
        title: d.title,
        publish_date: d.publish_date,
        summary: truncate(d.summary, 150),
        content_type: d.content_type,
        audience_level: d.audience_level,
        topics: d.topics,
        topics_proposed: d.topics_proposed,
        duration_seconds: d.duration_seconds,
        view_count_at_ingest: d.view_count_at_ingest,
        url: d.url,
        path: d.path,
        enriched: d.enriched,
      })),
    });
  } catch (e) {
    console.error('Filter error:', e);
    return res.status(500).json({ error: 'Filter failed' });
  }
};

function truncate(text: string, maxLength: number): string {
  return text.length > maxLength ? text.substring(0, maxLength) + '…' : text;
}
