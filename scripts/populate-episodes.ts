#!/usr/bin/env npx tsx
import { config } from "dotenv";
config({ path: ".env.local" });
/**
 * Populate episodes (metadata only) using yt-dlp
 *
 * Usage:
 *   npx tsx scripts/populate-episodes.ts --channel "https://www.youtube.com/@TheDiaryOfACEO"
 *   npx tsx scripts/populate-episodes.ts --channel "https://www.youtube.com/@TheDiaryOfACEO" --limit 50
 */

import { Command } from "commander";
import { execSync } from "child_process";
import { createClient } from "@supabase/supabase-js";

const program = new Command();

program
  .requiredOption("--channel <url>", "YouTube channel URL or handle (e.g. @TheDiaryOfACEO)")
  .option("--limit <n>", "Max number of videos to fetch", parseInt)
  .parse();

const opts = program.opts();

interface VideoMeta {
  id: string;
  title: string;
  description: string;
  thumbnail: string;
  duration: number;
  upload_date: string;
  channel: string;
  channel_id: string;
}

function fetchVideos(channelUrl: string, limit?: number): VideoMeta[] {
  // Normalize URL
  let url = channelUrl;
  if (url.startsWith("@")) url = `https://www.youtube.com/${url}`;
  if (!url.includes("/videos")) url = url.replace(/\/?$/, "/videos");

  const limitFlag = limit ? `--playlist-end ${limit}` : "";

  console.log(`Fetching video list from ${url}...`);
  const raw = execSync(
    `yt-dlp --flat-playlist --dump-json ${limitFlag} "${url}" 2>/dev/null`,
    { maxBuffer: 100 * 1024 * 1024 }
  ).toString();

  // Each line is a JSON object
  const entries = raw
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line));

  console.log(`Found ${entries.length} videos in playlist\n`);

  // flat-playlist gives minimal info — need to fetch full metadata
  // But for speed, use what we have and fill in missing fields
  return entries.map((e: any) => ({
    id: e.id,
    title: e.title ?? "Untitled",
    description: e.description ?? "",
    thumbnail: e.thumbnails?.[0]?.url ?? e.thumbnail ?? "",
    duration: e.duration ?? 0,
    upload_date: e.upload_date ?? "",
    channel: e.channel ?? e.uploader ?? "",
    channel_id: e.channel_id ?? e.uploader_id ?? "",
  }));
}

function formatDate(yyyymmdd: string): string | null {
  if (!yyyymmdd || yyyymmdd.length !== 8) return null;
  return `${yyyymmdd.slice(0, 4)}-${yyyymmdd.slice(4, 6)}-${yyyymmdd.slice(6, 8)}`;
}

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

async function main() {
  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

  const videos = fetchVideos(opts.channel, opts.limit);
  if (videos.length === 0) {
    console.log("No videos found.");
    return;
  }

  // Get channel info from first video's full metadata
  const firstId = videos[0].id;
  console.log(`Fetching channel info from video ${firstId}...`);
  const metaRaw = execSync(
    `yt-dlp --dump-json --skip-download "https://www.youtube.com/watch?v=${firstId}" 2>/dev/null`,
    { maxBuffer: 10 * 1024 * 1024 }
  ).toString();
  const meta = JSON.parse(metaRaw);
  const channelName = meta.channel || meta.uploader || "Unknown Channel";
  const channelYtId = meta.channel_id || meta.uploader_id || firstId;
  const slug = slugify(channelName);
  const thumbUrl = meta.channel_url
    ? undefined
    : undefined;

  // Upsert channel
  const { data: channel, error: chErr } = await supabase
    .from("channels")
    .upsert(
      {
        youtube_channel_id: channelYtId,
        name: channelName,
        slug,
      },
      { onConflict: "youtube_channel_id" }
    )
    .select()
    .single();

  if (chErr) {
    console.error("Failed to upsert channel:", chErr.message);
    process.exit(1);
  }
  console.log(`Channel: ${channel.name} (${channel.slug})\n`);

  // Batch upsert episodes
  const BATCH = 50;
  let inserted = 0;

  for (let i = 0; i < videos.length; i += BATCH) {
    const batch = videos.slice(i, i + BATCH).map((v) => ({
      channel_id: channel.id,
      youtube_id: v.id,
      title: v.title,
      description: v.description,
      thumbnail_url: v.thumbnail,
      duration_seconds: v.duration,
      published_at: formatDate(v.upload_date),
    }));

    const { error } = await supabase
      .from("episodes")
      .insert(batch);

    if (error) {
      console.error(`Batch ${Math.floor(i / BATCH) + 1} failed:`, error.message);
    } else {
      inserted += batch.length;
      console.log(`  Inserted ${inserted}/${videos.length}`);
    }
  }

  console.log(`\nDone! ${inserted} episodes populated for ${channel.name}.`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
