import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const { searchParams } = new URL(req.url);
  const diarizer = searchParams.get("diarizer");

  // Resolve episode UUID from id or youtube_id
  const isUUID = /^[0-9a-f]{8}-/.test(id);
  let episodeId = id;

  if (!isUUID) {
    const { data } = await supabase
      .from("episodes")
      .select("id")
      .eq("youtube_id", id)
      .single();
    if (!data) {
      return NextResponse.json([], { status: 200 });
    }
    episodeId = data.id;
  }

  let query = supabase
    .from("segments")
    .select("id, start_time, end_time, text, speaker, words, diarizer")
    .eq("episode_id", episodeId)
    .order("start_time", { ascending: true });

  if (diarizer) {
    query = query.eq("diarizer", diarizer);
  }

  const { data, error } = await query;

  if (error) {
    return NextResponse.json([], { status: 200 });
  }

  const segments = (data ?? []).map((row: any) => ({
    id: row.id,
    start_time: row.start_time,
    end_time: row.end_time,
    text: row.text,
    speaker: row.speaker,
    tag: row.diarizer,
    words: typeof row.words === "string" ? JSON.parse(row.words) : row.words,
    diarizer: row.diarizer,
  }));

  return NextResponse.json(segments);
}
