import { VercelRequest, VercelResponse } from '@vercel/node';
import entitiesData from '../generated/entities.json';

export default async function handler(req: VercelRequest, res: VercelResponse) {
  try {
    const { q, type, min_videos } = req.query;

    let entities = entitiesData;

    if (q) {
      const query = (q as string).toLowerCase();
      entities = entities.filter((e: any) =>
        e.name.toLowerCase().includes(query)
      );
    }

    if (type) {
      entities = entities.filter((e: any) => e.type === type);
    }

    if (min_videos) {
      const minCount = parseInt(min_videos as string, 10);
      entities = entities.filter((e: any) => e.count >= minCount);
    }

    res.status(200).json({
      entities: entities.sort((a: any, b: any) => b.count - a.count),
      total: entities.length,
    });
  } catch (error) {
    console.error('Error in /api/entities:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
}
