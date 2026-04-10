import { NextResponse } from 'next/server';
import { fetchOne, fetchAll, parseJsonb } from '@/lib/db';

type Episode = { id: string };
type YtSegmentRow = {
  id: string;
  position: number;
  start_time: number;
  end_time: number;
  text: string | null;
  words: unknown;
};

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id: youtubeId } = await params;

  const episode = await fetchOne<Episode>(
    'SELECT id FROM episodes WHERE youtube_id=$1',
    [youtubeId],
  );

  if (!episode) {
    return NextResponse.json({ error: 'Episode not found' }, { status: 404 });
  }

  const rows = await fetchAll<YtSegmentRow>(
    `SELECT id, position, start_time, end_time, text, words
       FROM yt_segments
      WHERE episode_id=$1
      ORDER BY start_time`,
    [episode.id],
  );

  // Legacy rows stored `words` as a JSONB *string* (double-encoded by the
  // pre-migration fetch_yt_captions.py). New rows store a real array.
  // Normalise both shapes here so the UI only sees arrays.
  const normalised = rows.map((r) => ({
    ...r,
    words: parseJsonb<unknown[]>(r.words) ?? [],
  }));

  return NextResponse.json(normalised);
}
