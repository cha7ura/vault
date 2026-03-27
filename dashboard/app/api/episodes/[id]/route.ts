import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  // Try by UUID first, then by youtube_id
  const isUUID = /^[0-9a-f]{8}-/.test(id);
  const col = isUUID ? "id" : "youtube_id";

  const { data, error } = await supabase
    .from("episodes")
    .select("id, youtube_id, title, duration_seconds")
    .eq(col, id)
    .single();

  if (error || !data) {
    return NextResponse.json({ error: "Episode not found" }, { status: 404 });
  }

  return NextResponse.json({
    id: data.id,
    youtube_id: data.youtube_id,
    title: data.title,
    status: "ready",
    duration: data.duration_seconds ?? null,
    intro_end_at: null,
  });
}
