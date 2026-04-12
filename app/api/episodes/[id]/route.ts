import { NextResponse } from "next/server";
import { fetchOne } from "@/lib/db";

type Episode = {
  id: string;
  youtube_id: string;
  title: string | null;
  duration_seconds: number | null;
};

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  // Try by UUID first, then by youtube_id (same heuristic as before).
  const isUUID = /^[0-9a-f]{8}-/.test(id);
  const episode = await fetchOne<Episode>(
    isUUID
      ? `SELECT id, youtube_id, title, duration_seconds
           FROM episodes WHERE id = $1`
      : `SELECT id, youtube_id, title, duration_seconds
           FROM episodes WHERE youtube_id = $1`,
    [id],
  );

  if (!episode) {
    return NextResponse.json({ error: "Episode not found" }, { status: 404 });
  }

  return NextResponse.json({
    id: episode.id,
    youtube_id: episode.youtube_id,
    title: episode.title,
    status: "ready",
    duration: episode.duration_seconds ?? null,
    intro_end_at: null,
  });
}
