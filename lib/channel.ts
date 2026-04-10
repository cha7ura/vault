/**
 * Shared `channels` row loader. Previously every page inlined its own
 * `getChannel(slug)` helper against Supabase; now they all go through here
 * so the SQL lives in exactly one place.
 */
import { fetchOne } from "@/lib/db";

export type Channel = {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  thumbnail_url: string | null;
  video_count: number | null;
  subscriber_count: number | null;
  last_synced_at: string | null;
  [key: string]: unknown;
};

export async function getChannelBySlug(slug: string): Promise<Channel | null> {
  return fetchOne<Channel>("SELECT * FROM channels WHERE slug = $1", [slug]);
}
