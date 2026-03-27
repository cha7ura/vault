import { NextResponse } from 'next/server';
import { supabase } from '@/lib/supabase';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id: youtubeId } = await params;
  const { searchParams } = new URL(request.url);
  const diarizer = searchParams.get('diarizer');

  const { data: episode } = await supabase
    .from('episodes')
    .select('id')
    .eq('youtube_id', youtubeId)
    .single();

  if (!episode) {
    return NextResponse.json({ error: 'Episode not found' }, { status: 404 });
  }

  let query = supabase
    .from('segments')
    .select('id, start_time, end_time, text, speaker, words, diarizer')
    .eq('episode_id', episode.id)
    .order('start_time');

  if (diarizer) {
    query = query.eq('diarizer', diarizer);
  }

  const { data, error } = await query;

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json(data || []);
}
