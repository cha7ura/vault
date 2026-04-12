import { NextRequest, NextResponse } from "next/server";
import { execute, executeReturning } from "@/lib/db";

type SegmentCorrection = {
  id: string;
  segment_id: string;
  episode_id: string;
  source: string;
  original_text: string | null;
  suggested_text: string | null;
  reason: string | null;
  status: string | null;
  reviewed_at: string | null;
  created_at: string;
};

export async function POST(request: NextRequest) {
  const body = await request.json();
  const {
    segment_id,
    episode_id,
    source,
    original_text,
    suggested_text,
    reason,
  } = body;

  const effectiveSource = source || "auto_merge_review";

  try {
    const correction = await executeReturning<SegmentCorrection>(
      `INSERT INTO segment_corrections
         (segment_id, episode_id, source, original_text, suggested_text, reason)
       VALUES ($1, $2, $3, $4, $5, $6)
       RETURNING *`,
      [
        segment_id,
        episode_id,
        effectiveSource,
        original_text,
        suggested_text,
        reason,
      ],
    );

    if (!correction) {
      return NextResponse.json(
        { error: "Failed to insert correction" },
        { status: 500 },
      );
    }

    // If this is an accepted auto-merge correction, apply it to the segment
    // and mark the correction row itself as accepted.
    if (suggested_text && effectiveSource === "auto_merge_review") {
      await execute(
        `UPDATE segments SET clean_text = $1 WHERE id = $2`,
        [suggested_text, segment_id],
      );
      await execute(
        `UPDATE segment_corrections
            SET status = 'accepted',
                reviewed_at = NOW()
          WHERE id = $1`,
        [correction.id],
      );
    }

    return NextResponse.json({ correction });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
