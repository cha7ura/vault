#!/usr/bin/env npx tsx
/**
 * Bulk Ingestion CLI - Multi-tenant
 *
 * Downloads and processes YouTube videos from ANY channel.
 *
 * Usage:
 *   npx tsx scripts/bulk-ingest.ts --channel "https://www.youtube.com/@TheDiaryOfACEO" --limit 10
 *   npx tsx scripts/bulk-ingest.ts --channel UCrPseYLGpNygVi34QpGNqpA --all
 *   npx tsx scripts/bulk-ingest.ts --video-id dQw4w9WgXcQ
 */

import { Command } from 'commander';
import { execSync } from 'child_process';
import { existsSync, mkdirSync, unlinkSync, readFileSync, writeFileSync } from 'fs';
import path from 'path';
import {
  fetchAllChannelVideos,
  parseDuration,
  getVideoById,
  getChannelInfo,
  resolveChannelId,
  generateChannelSlug,
  YouTubeVideo,
} from '../lib/youtube';
import { transcribeLocalAudio } from './transcribe-local';
import { extractAllContent, extractGuestInfo } from './extract-insights';
import { embed, embedBatch } from '../lib/openrouter';
import {
  fetchAll,
  fetchOne,
  execute,
  executeReturning,
  vecStr,
} from '../lib/db';
import { meilisearch, INDEXES, initializeIndexes } from '../lib/meilisearch';

// Configuration
const AUDIO_DIR = path.join(process.cwd(), '.audio-cache');
const PROGRESS_FILE = path.join(process.cwd(), '.ingest-progress.json');

interface ProgressData {
  channelId?: string;
  lastProcessedVideoId?: string;
  processedVideoIds: string[];
  lastRun: string;
}

interface ChannelRecord {
  id: string;
  youtube_channel_id: string;
  name: string;
  slug: string;
}

type EpisodeRow = { id: string };

/**
 * Extract URLs from text (for references)
 */
function extractUrlsFromText(text: string): string[] {
  const urlRegex = /(https?:\/\/[^\s]+)/g;
  return text.match(urlRegex) || [];
}

/**
 * Load progress data
 */
function loadProgress(channelId: string): ProgressData {
  const progressFile = `${PROGRESS_FILE}.${channelId}`;
  if (existsSync(progressFile)) {
    return JSON.parse(readFileSync(progressFile, 'utf-8'));
  }
  return { channelId, processedVideoIds: [], lastRun: new Date().toISOString() };
}

/**
 * Save progress data
 */
function saveProgress(progress: ProgressData): void {
  if (!progress.channelId) return;
  progress.lastRun = new Date().toISOString();
  const progressFile = `${PROGRESS_FILE}.${progress.channelId}`;
  writeFileSync(progressFile, JSON.stringify(progress, null, 2));
}

/**
 * Download audio from YouTube using yt-dlp
 */
async function downloadAudio(videoId: string): Promise<string> {
  if (!existsSync(AUDIO_DIR)) {
    mkdirSync(AUDIO_DIR, { recursive: true });
  }

  const outputPath = path.join(AUDIO_DIR, `${videoId}.mp3`);

  if (existsSync(outputPath)) {
    console.log(`  Audio already cached: ${outputPath}`);
    return outputPath;
  }

  const videoUrl = `https://www.youtube.com/watch?v=${videoId}`;

  console.log(`  Downloading audio for ${videoId}...`);

  try {
    execSync(
      `yt-dlp -x --audio-format mp3 --audio-quality 0 -o "${outputPath}" "${videoUrl}"`,
      { stdio: 'pipe' }
    );

    console.log(`  ✓ Audio downloaded: ${outputPath}`);
    return outputPath;
  } catch (error: any) {
    throw new Error(`Failed to download audio: ${error.message}`);
  }
}

/**
 * Clean up audio file
 */
function cleanupAudio(audioPath: string): void {
  try {
    if (existsSync(audioPath)) {
      unlinkSync(audioPath);
      console.log(`  Cleaned up: ${audioPath}`);
    }
  } catch {
    console.warn(`  Warning: Could not clean up ${audioPath}`);
  }
}

/**
 * Get or create channel in database
 */
async function getOrCreateChannel(
  youtubeChannelId: string,
): Promise<ChannelRecord> {
  // Check if channel exists
  const existing = await fetchOne<ChannelRecord>(
    `SELECT id, youtube_channel_id, name, slug
       FROM channels
      WHERE youtube_channel_id = $1`,
    [youtubeChannelId],
  );

  if (existing) {
    return existing;
  }

  // Fetch channel info from YouTube
  console.log('Fetching channel info from YouTube...');
  const channelInfo = await getChannelInfo(youtubeChannelId);

  // Create channel
  const slug = generateChannelSlug(channelInfo.title);
  const newChannel = await executeReturning<ChannelRecord>(
    `INSERT INTO channels
       (youtube_channel_id, name, slug, description,
        thumbnail_url, banner_url, subscriber_count, video_count)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
     RETURNING id, youtube_channel_id, name, slug`,
    [
      youtubeChannelId,
      channelInfo.title,
      slug,
      channelInfo.description,
      channelInfo.thumbnailUrl,
      channelInfo.bannerUrl,
      channelInfo.subscriberCount,
      channelInfo.videoCount,
    ],
  );

  if (!newChannel) {
    throw new Error('Failed to create channel');
  }

  console.log(`✓ Created channel: ${channelInfo.title} (${slug})`);
  return newChannel;
}

/**
 * Build a multi-row INSERT with positional placeholders. Callers may pass
 * `casts` keyed by column *index* to apply a per-column type cast (e.g.
 * `{ 5: 'vector' }` to render the 6th placeholder as `$N::vector`) which
 * is how pgvector values are inserted alongside regular columns.
 */
function buildMultiRowInsert(
  table: string,
  columns: string[],
  rows: unknown[][],
  casts: Record<number, string> = {},
): { sql: string; params: unknown[] } {
  const colList = columns.join(', ');
  const placeholders: string[] = [];
  const params: unknown[] = [];

  rows.forEach((row, i) => {
    const slots = row.map((_, j) => {
      const ph = `$${i * columns.length + j + 1}`;
      return casts[j] ? `${ph}::${casts[j]}` : ph;
    });
    placeholders.push(`(${slots.join(', ')})`);
    params.push(...row);
  });

  const sql = `INSERT INTO ${table} (${colList}) VALUES ${placeholders.join(', ')}`;
  return { sql, params };
}

/**
 * Process a single video
 */
async function processVideo(
  video: YouTubeVideo,
  channel: ChannelRecord,
  options: { keepAudio?: boolean },
): Promise<boolean> {
  let audioPath: string | null = null;

  try {
    console.log(`\n📹 Processing: ${video.title}`);
    console.log(`   Video ID: ${video.id}`);
    console.log(`   Channel: ${channel.name}`);

    // Step 1: Download audio
    audioPath = await downloadAudio(video.id);

    // Step 2: Transcribe
    console.log('  Transcribing with Deepgram...');
    const transcript = await transcribeLocalAudio(audioPath, {
      diarize: true,
    });
    console.log(`  ✓ Transcribed: ${transcript.text.length} characters`);

    // Step 3: Extract insights
    console.log('  Extracting insights with AI...');
    const extracted = await extractAllContent(transcript.text, video.description);
    console.log(
      `  ✓ Extracted: ${extracted.frameworks.length} frameworks, ${extracted.insights.length} insights, ${extracted.books.length} books`,
    );

    // Step 3b: Extract guest info
    console.log('  Extracting guest information...');
    const guests = await extractGuestInfo(transcript.text, video.title);
    console.log(`  ✓ Found ${guests.length} guest(s)`);

    // Step 4: Generate embeddings
    console.log('  Generating embeddings...');
    const textForEmbedding =
      video.title + ' ' + video.description + ' ' + transcript.text.substring(0, 5000);
    const [episodeEmbedding, insightEmbeddings] = await Promise.all([
      embed(textForEmbedding),
      extracted.insights.length > 0
        ? embedBatch(extracted.insights.map((i) => i.title + ' ' + i.content))
        : Promise.resolve([] as number[][]),
    ]);
    console.log('  ✓ Embeddings generated');

    // Step 5: Store in Postgres
    console.log('  Storing in database...');
    const durationSeconds = parseDuration(video.duration);

    // Upsert episode. Uses the `channels.id, youtube_id` composite unique
    // index (the same one the old Supabase upsert used via onConflict).
    const episode = await executeReturning<EpisodeRow>(
      `INSERT INTO episodes
         (channel_id, youtube_id, title, description, thumbnail_url,
          duration_seconds, published_at, transcript, transcript_formatted,
          embedding, "references", processed_at)
       VALUES
         ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::vector, $11::jsonb, NOW())
       ON CONFLICT (channel_id, youtube_id) DO UPDATE SET
         title = EXCLUDED.title,
         description = EXCLUDED.description,
         thumbnail_url = EXCLUDED.thumbnail_url,
         duration_seconds = EXCLUDED.duration_seconds,
         published_at = EXCLUDED.published_at,
         transcript = EXCLUDED.transcript,
         transcript_formatted = EXCLUDED.transcript_formatted,
         embedding = EXCLUDED.embedding,
         "references" = EXCLUDED."references",
         processed_at = EXCLUDED.processed_at
       RETURNING id`,
      [
        channel.id,
        video.id,
        video.title,
        video.description,
        video.thumbnailUrl,
        durationSeconds,
        video.publishedAt,
        transcript.text,
        extracted.formattedTranscript,
        vecStr(episodeEmbedding),
        JSON.stringify(extractUrlsFromText(video.description)),
      ],
    );

    if (!episode) {
      throw new Error('Failed to insert episode');
    }

    // Insert insights. Delete-then-insert preserves the Supabase semantics
    // where a re-run of the ingester fully replaces the episode's insights.
    if (extracted.insights.length > 0) {
      await execute(`DELETE FROM insights WHERE episode_id = $1`, [episode.id]);

      const rows = extracted.insights.map((insight, idx) => [
        episode.id,
        insight.type,
        insight.title,
        insight.content,
        insight.timestamp,
        vecStr(insightEmbeddings[idx] ?? []),
      ]);
      const { sql, params } = buildMultiRowInsert(
        'insights',
        ['episode_id', 'type', 'title', 'content', 'start_time_seconds', 'embedding'],
        rows,
        { 5: 'vector' },
      );
      await execute(sql, params);
    }

    // Insert frameworks as insights
    if (extracted.frameworks.length > 0) {
      const frameworkEmbeddings = await embedBatch(
        extracted.frameworks.map((f) => f.title + ' ' + f.content),
      );

      const rows = extracted.frameworks.map((framework, idx) => [
        episode.id,
        'framework',
        framework.title,
        framework.content,
        framework.timestamp,
        vecStr(frameworkEmbeddings[idx] ?? []),
      ]);
      const { sql, params } = buildMultiRowInsert(
        'insights',
        ['episode_id', 'type', 'title', 'content', 'start_time_seconds', 'embedding'],
        rows,
        { 5: 'vector' },
      );
      await execute(sql, params);
    }

    // Insert books
    if (extracted.books.length > 0) {
      await execute(`DELETE FROM books WHERE episode_id = $1`, [episode.id]);
      const rows = extracted.books.map((book) => [
        episode.id,
        book.title,
        book.author,
        book.context,
        book.timestamp,
      ]);
      const { sql, params } = buildMultiRowInsert(
        'books',
        ['episode_id', 'title', 'author', 'context', 'timestamp_seconds'],
        rows,
      );
      await execute(sql, params);
    }

    // Insert papers
    if (extracted.papers.length > 0) {
      await execute(`DELETE FROM papers WHERE episode_id = $1`, [episode.id]);
      const rows = extracted.papers.map((paper) => [
        episode.id,
        paper.title,
        paper.authors,
        paper.url,
        paper.context,
        paper.timestamp,
      ]);
      const { sql, params } = buildMultiRowInsert(
        'papers',
        ['episode_id', 'title', 'authors', 'url', 'context', 'timestamp_seconds'],
        rows,
      );
      await execute(sql, params);
    }

    // Store guest info (with channel_id)
    if (guests.length > 0) {
      for (const guest of guests) {
        const slug = guest.name
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, '-')
          .replace(/(^-|-$)/g, '');

        // Check if guest already exists for this channel
        const existingGuest = await fetchOne<{ id: string }>(
          `SELECT id FROM guests WHERE channel_id = $1 AND slug = $2`,
          [channel.id, slug],
        );

        let guestId: string;

        if (existingGuest) {
          guestId = existingGuest.id;
        } else {
          try {
            const newGuest = await executeReturning<{ id: string }>(
              `INSERT INTO guests (channel_id, name, slug, bio)
               VALUES ($1, $2, $3, $4)
               RETURNING id`,
              [
                channel.id,
                guest.name,
                slug,
                guest.role
                  ? `${guest.role}${guest.company ? ` at ${guest.company}` : ''}`
                  : null,
              ],
            );
            if (!newGuest) continue;
            guestId = newGuest.id;
          } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            console.warn(`  Warning: Could not create guest ${guest.name}: ${message}`);
            continue;
          }
        }

        await execute(
          `INSERT INTO episode_guests (episode_id, guest_id)
           VALUES ($1, $2)
           ON CONFLICT (episode_id, guest_id) DO NOTHING`,
          [episode.id, guestId],
        );
      }
    }

    console.log('  ✓ Stored in database');

    // Step 6: Index in Meilisearch with channel info
    console.log('  Indexing in Meilisearch...');
    await meilisearch.index(INDEXES.episodes).addDocuments([
      {
        id: episode.id,
        channel_id: channel.id,
        channel_slug: channel.slug,
        youtube_id: video.id,
        title: video.title,
        description: video.description,
        thumbnail_url: video.thumbnailUrl,
        published_at: video.publishedAt,
        duration_seconds: durationSeconds,
      },
    ]);
    console.log('  ✓ Indexed in Meilisearch');

    // Clean up
    if (!options.keepAudio && audioPath) {
      cleanupAudio(audioPath);
    }

    console.log(`✅ Completed: ${video.id}`);
    return true;
  } catch (error: any) {
    console.error(`❌ Failed to process ${video.id}: ${error.message}`);

    if (audioPath && !options.keepAudio) {
      cleanupAudio(audioPath);
    }

    return false;
  }
}

/**
 * Main CLI
 */
async function main() {
  const program = new Command();

  program
    .name('bulk-ingest')
    .description('Bulk ingest YouTube videos from any channel into Vault')
    .version('2.0.0')
    .requiredOption('-c, --channel <url>', 'YouTube channel URL or ID (required)')
    .option('-l, --limit <number>', 'Maximum number of videos to process', (v) => parseInt(v, 10))
    .option('-a, --all', 'Process all videos from the channel')
    .option('-s, --skip-existing', 'Skip videos that have already been processed')
    .option('-v, --video-id <id>', 'Process a specific video by ID')
    .option('-k, --keep-audio', 'Keep downloaded audio files after processing')
    .option('--dry-run', 'Show what would be processed without actually processing')
    .option('--resume', 'Resume from last progress checkpoint')
    .parse(process.argv);

  const options = program.opts();

  console.log('🚀 Vault Bulk Ingestion');
  console.log('=======================\n');

  // Check required environment variables
  const requiredEnvVars = [
    'YOUTUBE_API_KEY',
    'DEEPGRAM_API_KEY',
    'OPENROUTER_API_KEY',
    'AIVEN_DATABASE_URL',
  ];

  for (const envVar of requiredEnvVars) {
    if (!process.env[envVar]) {
      console.error(`❌ Missing required environment variable: ${envVar}`);
      process.exit(1);
    }
  }

  // Check yt-dlp is installed
  try {
    execSync('yt-dlp --version', { stdio: 'pipe' });
  } catch {
    console.error('❌ yt-dlp is not installed. Install it with:');
    console.error('   brew install yt-dlp  (macOS)');
    console.error('   pip install yt-dlp   (pip)');
    process.exit(1);
  }

  // Resolve channel ID
  console.log(`Resolving channel: ${options.channel}`);
  const youtubeChannelId = await resolveChannelId(options.channel);
  console.log(`✓ YouTube Channel ID: ${youtubeChannelId}\n`);

  // Initialize services
  await initializeIndexes();

  // Get or create channel
  const channel = await getOrCreateChannel(youtubeChannelId);
  console.log(`📺 Channel: ${channel.name} (${channel.slug})\n`);

  // Load progress
  const progress = options.resume
    ? loadProgress(youtubeChannelId)
    : { channelId: youtubeChannelId, processedVideoIds: [], lastRun: new Date().toISOString() };

  // Get videos to process
  let videos: YouTubeVideo[] = [];

  if (options.videoId) {
    console.log(`Fetching video: ${options.videoId}`);
    const video = await getVideoById(options.videoId);
    if (!video) {
      console.error(`❌ Video not found: ${options.videoId}`);
      process.exit(1);
    }
    videos = [video];
  } else {
    const limit = options.all ? undefined : options.limit || 10;
    console.log(`Fetching ${limit ? `up to ${limit}` : 'all'} videos from channel...`);
    videos = await fetchAllChannelVideos(youtubeChannelId, limit);
  }

  console.log(`\nFound ${videos.length} videos to process\n`);

  // Filter out already processed
  if (options.skipExisting) {
    const existingEpisodes = await fetchAll<{ youtube_id: string }>(
      `SELECT youtube_id
         FROM episodes
        WHERE channel_id = $1
          AND processed_at IS NOT NULL`,
      [channel.id],
    );

    const existingIds = new Set(existingEpisodes.map((e) => e.youtube_id));
    const originalCount = videos.length;
    videos = videos.filter((v) => !existingIds.has(v.id));
    console.log(`Skipping ${originalCount - videos.length} already processed videos\n`);
  }

  // Filter based on local progress if resuming
  if (options.resume && progress.processedVideoIds.length > 0) {
    const progressIds = new Set(progress.processedVideoIds);
    videos = videos.filter((v) => !progressIds.has(v.id));
    console.log(`Resuming: Skipping ${progress.processedVideoIds.length} previously processed videos\n`);
  }

  if (videos.length === 0) {
    console.log('✅ No new videos to process!');
    return;
  }

  // Dry run mode
  if (options.dryRun) {
    console.log('Dry run - would process these videos:\n');
    videos.forEach((v, i) => {
      console.log(`${i + 1}. ${v.title} (${v.id})`);
    });
    return;
  }

  // Process videos
  let successCount = 0;
  let failCount = 0;

  for (let i = 0; i < videos.length; i++) {
    const video = videos[i];
    console.log(`\n[${i + 1}/${videos.length}]`);

    const success = await processVideo(video, channel, {
      keepAudio: options.keepAudio,
    });

    if (success) {
      successCount++;
      progress.processedVideoIds.push(video.id);
      progress.lastProcessedVideoId = video.id;
      saveProgress(progress);
    } else {
      failCount++;
    }

    if (i < videos.length - 1) {
      console.log('\n⏳ Waiting 2 seconds before next video...');
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  }

  // Update channel last_synced_at
  await execute(
    `UPDATE channels SET last_synced_at = NOW() WHERE id = $1`,
    [channel.id],
  );

  // Summary
  console.log('\n=======================');
  console.log('📊 Ingestion Summary');
  console.log('=======================');
  console.log(`📺 Channel: ${channel.name}`);
  console.log(`✅ Successful: ${successCount}`);
  console.log(`❌ Failed: ${failCount}`);
  console.log(`📁 Total: ${videos.length}`);
}

main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
