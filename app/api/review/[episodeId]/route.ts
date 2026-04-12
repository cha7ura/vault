import { NextRequest, NextResponse } from "next/server";
import { fetchOne, fetchAll } from "@/lib/db";

type Episode = {
  id: string;
  youtube_id: string;
  title: string | null;
  intro_end_position: number | null;
  quality_issues: unknown;
};

type FlaggedSegment = {
  id: string;
  position: number;
  speaker: string | null;
  text: string | null;
  clean_text: string | null;
  text_confidence: number | null;
  start_time: number;
  end_time: number;
  person_id: string | null;
};

type YtRow = {
  position: number;
  text: string | null;
};

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ episodeId: string }> },
) {
  const { episodeId } = await params;

  // Resolve by youtube_id or UUID. Supabase version flipped the filter
  // column based on length; preserving that heuristic here.
  const isUUID = episodeId.length >= 36;
  const episode = await fetchOne<Episode>(
    isUUID
      ? `SELECT id, youtube_id, title, intro_end_position, quality_issues
           FROM episodes WHERE id = $1`
      : `SELECT id, youtube_id, title, intro_end_position, quality_issues
           FROM episodes WHERE youtube_id = $1`,
    [episodeId],
  );

  if (!episode) {
    return NextResponse.json({ error: "Episode not found" }, { status: 404 });
  }

  // Flagged (low-confidence) segments
  const segments = await fetchAll<FlaggedSegment>(
    `SELECT id, position, speaker, text, clean_text, text_confidence,
            start_time, end_time, person_id
       FROM segments
      WHERE episode_id = $1
        AND text_confidence < 0.85
      ORDER BY position`,
    [episode.id],
  );

  // Matching YT captions. Old code did `.in('position', positions)` — with
  // raw SQL we can express the same with ANY($2::int[]), which also avoids
  // the old "positions.length > 0 ? positions : [-1]" sentinel hack.
  const positions = segments.map((s) => s.position);
  const ytSegments =
    positions.length > 0
      ? await fetchAll<YtRow>(
          `SELECT position, text
             FROM yt_segments
            WHERE episode_id = $1
              AND position = ANY($2::int[])`,
          [episode.id, positions],
        )
      : [];

  const ytByPos = Object.fromEntries(
    ytSegments.map((s) => [s.position, s.text]),
  );

  return NextResponse.json({
    episode,
    segments: segments.map((s) => ({
      ...s,
      yt_text: ytByPos[s.position] || "",
    })),
  });
}
