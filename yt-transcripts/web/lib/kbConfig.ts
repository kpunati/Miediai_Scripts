export type DigestRow = {
  video_id: string;
  channel_slug: string;
  channel_name: string;
  title: string;
  publish_date: string;
  duration_seconds: number;
  view_count_at_ingest: number;
  content_type: string;
  audience_level: string;
  topics: string[];
  topics_proposed: string[];
  summary: string;
  url: string;
  path: string;
  full_path: string;
  enriched: boolean;
  flags: string[];
};

export type ChannelRow = {
  channel_slug: string;
  channel_name: string;
  count: number;
  enriched_count: number;
  date_range: {
    earliest: string;
    latest: string;
  };
  top_topics: string[];
};

export type IndexRow = DigestRow & {
  entities: {
    people: Array<{ name: string; role?: string }>;
    companies: Array<{ name: string; ticker?: string }>;
    tickers: string[];
    funds: Array<{ name: string; ticker?: string }>;
    products: string[];
    concepts: string[];
  };
  key_claims: Array<{
    claim: string;
    timestamp: string;
    confidence: 'high' | 'medium' | 'low';
    flagged: boolean;
  }>;
};

export type SearchIndexEntry = {
  id: string;
  video_id: string;
  channel_slug: string;
  channel_name: string;
  title: string;
  summary: string;
  topics_str: string;
  publish_date: string;
};

export const SEARCH_OPTIONS = {
  fields: ['title', 'channel_name', 'summary', 'topics_str'],
  storeFields: [
    'id',
    'video_id',
    'channel_slug',
    'channel_name',
    'title',
    'summary',
    'publish_date',
  ],
};

export function parseCSVRow(
  line: string,
  headers: string[]
): Partial<DigestRow> | null {
  const values = parseCSVLine(line);
  if (values.length < headers.length) return null;

  const row: Record<string, any> = {};
  headers.forEach((h, i) => {
    row[h] = values[i];
  });

  return {
    video_id: row.video_id,
    channel_slug: row.channel_slug,
    channel_name: row.channel_name,
    title: row.title,
    publish_date: row.publish_date,
    duration_seconds: parseInt(row.duration_seconds, 10),
    view_count_at_ingest: parseInt(row.view_count_at_ingest, 10),
    content_type: row.content_type,
    audience_level: row.audience_level,
    topics: (row.topics || '')
      .split(';')
      .map((t: string) => t.trim())
      .filter(Boolean),
    topics_proposed: (row.topics_proposed || '')
      .split(';')
      .map((t: string) => t.trim())
      .filter(Boolean),
    summary: row.summary,
    url: row.url,
    enriched: row.enriched === 'True' || row.enriched === 'true',
    flags: (row.flags || '')
      .split(';')
      .map((f: string) => f.trim())
      .filter(Boolean),
  };
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
