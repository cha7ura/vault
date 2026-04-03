import { createClient } from "@supabase/supabase-js";
import { NextRequest, NextResponse } from "next/server";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ episodeId: string }> }
) {
  const { episodeId } = await params;

  // Resolve by youtube_id or UUID
  let episodeFilter = "id";
  if (episodeId.length < 36) {
    episodeFilter = "youtube_id";
  }

  const { data: episode } = await supabase
    .from("episodes")
    .select("id, youtube_id, title, intro_end_position, quality_issues")
    .eq(episodeFilter, episodeId)
    .single();

  if (!episode) {
    return NextResponse.json({ error: "Episode not found" }, { status: 404 });
  }

  // Fetch flagged segments (low confidence)
  const { data: segments } = await supabase
    .from("segments")
    .select(
      "id, position, speaker, text, clean_text, text_confidence, start_time, end_time, person_id"
    )
    .eq("episode_id", episode.id)
    .lt("text_confidence", 0.85)
    .order("position");

  // Fetch matching YT segments
  const positions = (segments || []).map((s) => s.position);
  const { data: ytSegments } = await supabase
    .from("yt_segments")
    .select("position, text")
    .eq("episode_id", episode.id)
    .in("position", positions.length > 0 ? positions : [-1]);

  const ytByPos = Object.fromEntries(
    (ytSegments || []).map((s) => [s.position, s.text])
  );

  return NextResponse.json({
    episode,
    segments: (segments || []).map((s) => ({
      ...s,
      yt_text: ytByPos[s.position] || "",
    })),
  });
}
