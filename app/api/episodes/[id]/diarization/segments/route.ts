import { NextResponse } from "next/server";
import { fetchOne, fetchAll, parseJsonb } from "@/lib/db";

type SegmentRow = {
  id: string;
  start_time: number;
  end_time: number;
  text: string | null;
  speaker: string | null;
  words: unknown;
  diarizer: string | null;
};

export async function GET(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const { searchParams } = new URL(req.url);
  const diarizer = searchParams.get("diarizer");

  // Resolve episode UUID from id or youtube_id.
  const isUUID = /^[0-9a-f]{8}-/.test(id);
  let episodeId = id;

  if (!isUUID) {
    const episode = await fetchOne<{ id: string }>(
      `SELECT id FROM episodes WHERE youtube_id = $1`,
      [id],
    );
    if (!episode) {
      return NextResponse.json([], { status: 200 });
    }
    episodeId = episode.id;
  }

  try {
    const rows = diarizer
      ? await fetchAll<SegmentRow>(
          `SELECT id, start_time, end_time, text, speaker, words, diarizer
             FROM segments
            WHERE episode_id = $1
              AND diarizer = $2
            ORDER BY start_time ASC`,
          [episodeId, diarizer],
        )
      : await fetchAll<SegmentRow>(
          `SELECT id, start_time, end_time, text, speaker, words, diarizer
             FROM segments
            WHERE episode_id = $1
            ORDER BY start_time ASC`,
          [episodeId],
        );

    // `words` may be legacy double-encoded jsonb (stored as a JSON string)
    // from the pre-migration path — parseJsonb handles both shapes.
    const segments = rows.map((row) => ({
      id: row.id,
      start_time: row.start_time,
      end_time: row.end_time,
      text: row.text,
      speaker: row.speaker,
      tag: row.diarizer,
      words: parseJsonb(row.words),
      diarizer: row.diarizer,
    }));

    return NextResponse.json(segments);
  } catch (err) {
    console.error("diarization/segments query failed:", err);
    return NextResponse.json([], { status: 200 });
  }
}
