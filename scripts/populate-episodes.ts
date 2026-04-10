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
import { execute, executeReturning } from "@/lib/db";

const program = new Command();

program
  .requiredOption("--channel <url>", "YouTube channel URL or handle (e.g. @TheDiaryOfACEO)")
  .option("--limit <n>", "Max number of videos to fetch", (v) => parseInt(v, 10))
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

type Channel = {
  id: string;
  youtube_channel_id: string;
  name: string;
  slug: string;
};

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

  // Upsert channel (on conflict = youtube_channel_id, update name & slug).
  const channel = await executeReturning<Channel>(
    `INSERT INTO channels (youtube_channel_id, name, slug)
     VALUES ($1, $2, $3)
     ON CONFLICT (youtube_channel_id) DO UPDATE
        SET name = EXCLUDED.name,
            slug = EXCLUDED.slug
     RETURNING id, youtube_channel_id, name, slug`,
    [channelYtId, channelName, slug],
  );

  if (!channel) {
    console.error("Failed to upsert channel");
    process.exit(1);
  }
  console.log(`Channel: ${channel.name} (${channel.slug})\n`);

  // Batch insert episodes. Builds a multi-row VALUES clause so each batch
  // hits the db with a single round trip.
  const BATCH = 50;
  let inserted = 0;

  for (let i = 0; i < videos.length; i += BATCH) {
    const batch = videos.slice(i, i + BATCH);
    const values: unknown[] = [];
    const placeholders: string[] = [];

    batch.forEach((v, j) => {
      const base = j * 7;
      placeholders.push(
        `($${base + 1}, $${base + 2}, $${base + 3}, $${base + 4}, $${base + 5}, $${base + 6}, $${base + 7})`,
      );
      values.push(
        channel.id,
        v.id,
        v.title,
        v.description,
        v.thumbnail,
        v.duration,
        formatDate(v.upload_date),
      );
    });

    try {
      const affected = await execute(
        `INSERT INTO episodes
           (channel_id, youtube_id, title, description,
            thumbnail_url, duration_seconds, published_at)
         VALUES ${placeholders.join(", ")}
         ON CONFLICT (channel_id, youtube_id) DO NOTHING`,
        values,
      );
      inserted += affected;
      console.log(`  Inserted ${inserted}/${videos.length}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error(`Batch ${Math.floor(i / BATCH) + 1} failed:`, message);
    }
  }

  console.log(`\nDone! ${inserted} episodes populated for ${channel.name}.`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
