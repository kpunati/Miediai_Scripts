import { VercelRequest, VercelResponse } from '@vercel/node';
import topicsData from '../generated/topics.json';

export default async function handler(req: VercelRequest, res: VercelResponse) {
  try {
    const { q, min_videos } = req.query;

    let topics = topicsData;

    if (q) {
      const query = (q as string).toLowerCase();
      topics = topics.filter((t: any) =>
        t.topic.toLowerCase().includes(query)
      );
    }

    if (min_videos) {
      const minCount = parseInt(min_videos as string, 10);
      topics = topics.filter((t: any) => t.count >= minCount);
    }

    res.status(200).json({
      topics: topics.sort((a: any, b: any) => b.count - a.count),
      total: topics.length,
    });
  } catch (error) {
    console.error('Error in /api/topics:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
}
