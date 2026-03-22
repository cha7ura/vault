import { NextResponse } from 'next/server';
import { supabase } from '@/lib/supabase';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id: youtubeId } = await params;

  const { data: episode } = await supabase
    .from('episodes')
    .select('id')
    .eq('youtube_id', youtubeId)
    .single();

  if (!episode) {
    return NextResponse.json({ error: 'Episode not found' }, { status: 404 });
  }

  const { data, error } = await supabase
    .from('yt_segments')
    .select('id, position, start_time, end_time, text, words')
    .eq('episode_id', episode.id)
    .order('start_time');

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json(data || []);
}
