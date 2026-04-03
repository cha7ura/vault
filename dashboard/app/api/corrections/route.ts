import { createClient } from "@supabase/supabase-js";
import { NextRequest, NextResponse } from "next/server";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { segment_id, episode_id, source, original_text, suggested_text, reason } =
    body;

  const { data, error } = await supabase
    .from("segment_corrections")
    .insert({
      segment_id,
      episode_id,
      source: source || "auto_merge_review",
      original_text,
      suggested_text,
      reason,
    })
    .select()
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  // If this is an accepted correction, update the segment directly
  if (suggested_text && source === "auto_merge_review") {
    await supabase
      .from("segments")
      .update({ clean_text: suggested_text })
      .eq("id", segment_id);

    await supabase
      .from("segment_corrections")
      .update({ status: "accepted", reviewed_at: new Date().toISOString() })
      .eq("id", data.id);
  }

  return NextResponse.json({ correction: data });
}
