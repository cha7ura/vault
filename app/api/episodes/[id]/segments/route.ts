import { NextResponse } from 'next/server';
import { fetchOne, fetchAll } from '@/lib/db';

type Episode = { id: string };
type Segment = {
  id: string;
  start_time: number;
  end_time: number;
  text: string | null;
  speaker: string | null;
  words: unknown;
  diarizer: string | null;
};

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id: youtubeId } = await params;
  const { searchParams } = new URL(request.url);
  const diarizer = searchParams.get('diarizer');

  const episode = await fetchOne<Episode>(
    'SELECT id FROM episodes WHERE youtube_id=$1',
    [youtubeId],
  );

  if (!episode) {
    return NextResponse.json({ error: 'Episode not found' }, { status: 404 });
  }

  const segments = diarizer
    ? await fetchAll<Segment>(
        `SELECT id, start_time, end_time, text, speaker, words, diarizer
           FROM segments
          WHERE episode_id=$1 AND diarizer=$2
          ORDER BY start_time`,
        [episode.id, diarizer],
      )
    : await fetchAll<Segment>(
        `SELECT id, start_time, end_time, text, speaker, words, diarizer
           FROM segments
          WHERE episode_id=$1
          ORDER BY start_time`,
        [episode.id],
      );

  return NextResponse.json(segments);
}
