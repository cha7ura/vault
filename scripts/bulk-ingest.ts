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
  fetchChannelVideos, 
  fetchAllChannelVideos,
  parseDuration, 
  getVideoById, 
  getChannelInfo,
  resolveChannelId,
  generateChannelSlug,
  YouTubeVideo 
} from '../lib/youtube';
import { transcribeLocalAudio } from './transcribe-local';
import { extractAllContent, extractGuestInfo } from './extract-insights';
import { embed, embedBatch } from '../lib/openrouter';
import { createServerClient } from '../lib/supabase';
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
  } catch (error) {
    console.warn(`  Warning: Could not clean up ${audioPath}`);
  }
}

/**
 * Get or create channel in database
 */
async function getOrCreateChannel(
  serverClient: ReturnType<typeof createServerClient>,
  youtubeChannelId: string
): Promise<ChannelRecord> {
  // Check if channel exists
  const { data: existing } = await serverClient
    .from('channels')
    .select('id, youtube_channel_id, name, slug')
    .eq('youtube_channel_id', youtubeChannelId)
    .single();

  if (existing) {
    return existing;
  }

  // Fetch channel info from YouTube
  console.log('Fetching channel info from YouTube...');
  const channelInfo = await getChannelInfo(youtubeChannelId);
  
  // Create channel
  const slug = generateChannelSlug(channelInfo.title);
  const { data: newChannel, error } = await serverClient
    .from('channels')
    .insert({
      youtube_channel_id: youtubeChannelId,
      name: channelInfo.title,
      slug: slug,
      description: channelInfo.description,
      thumbnail_url: channelInfo.thumbnailUrl,
      banner_url: channelInfo.bannerUrl,
      subscriber_count: channelInfo.subscriberCount,
      video_count: channelInfo.videoCount,
    })
    .select()
    .single();

  if (error) {
    throw new Error(`Failed to create channel: ${error.message}`);
  }

  console.log(`✓ Created channel: ${channelInfo.title} (${slug})`);
  return newChannel;
}

/**
 * Process a single video
 */
async function processVideo(
  video: YouTubeVideo,
  channel: ChannelRecord,
  serverClient: ReturnType<typeof createServerClient>,
  options: { keepAudio?: boolean }
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
    console.log(`  ✓ Extracted: ${extracted.frameworks.length} frameworks, ${extracted.insights.length} insights, ${extracted.books.length} books`);

    // Step 3b: Extract guest info
    console.log('  Extracting guest information...');
    const guests = await extractGuestInfo(transcript.text, video.title);
    console.log(`  ✓ Found ${guests.length} guest(s)`);

    // Step 4: Generate embeddings
    console.log('  Generating embeddings...');
    const textForEmbedding = video.title + ' ' + video.description + ' ' + transcript.text.substring(0, 5000);
    const [episodeEmbedding, insightEmbeddings] = await Promise.all([
      embed(textForEmbedding),
      extracted.insights.length > 0 
        ? embedBatch(extracted.insights.map(i => i.title + ' ' + i.content))
        : Promise.resolve([]),
    ]);
    console.log('  ✓ Embeddings generated');

    // Step 5: Store in Supabase
    console.log('  Storing in Supabase...');
    const durationSeconds = parseDuration(video.duration);

    // Upsert episode with channel_id
    const { data: episode, error: episodeError } = await serverClient
      .from('episodes')
      .upsert({
        channel_id: channel.id,
        youtube_id: video.id,
        title: video.title,
        description: video.description,
        thumbnail_url: video.thumbnailUrl,
        duration_seconds: durationSeconds,
        published_at: video.publishedAt,
        transcript: transcript.text,
        transcript_formatted: extracted.formattedTranscript,
        embedding: episodeEmbedding,
        references: extractUrlsFromText(video.description),
        processed_at: new Date().toISOString(),
      }, { onConflict: 'channel_id,youtube_id' })
      .select()
      .single();

    if (episodeError) {
      throw new Error(`Failed to insert episode: ${episodeError.message}`);
    }

    // Insert insights
    if (extracted.insights.length > 0) {
      await serverClient.from('insights').delete().eq('episode_id', episode.id);
      
      const insightsToInsert = extracted.insights.map((insight, idx) => ({
        episode_id: episode.id,
        type: insight.type,
        title: insight.title,
        content: insight.content,
        start_time_seconds: insight.timestamp,
        embedding: insightEmbeddings[idx],
      }));

      await serverClient.from('insights').insert(insightsToInsert);
    }

    // Insert frameworks as insights
    if (extracted.frameworks.length > 0) {
      const frameworkEmbeddings = await embedBatch(
        extracted.frameworks.map(f => f.title + ' ' + f.content)
      );

      const frameworksToInsert = extracted.frameworks.map((framework, idx) => ({
        episode_id: episode.id,
        type: 'framework' as const,
        title: framework.title,
        content: framework.content,
        start_time_seconds: framework.timestamp,
        embedding: frameworkEmbeddings[idx],
      }));

      await serverClient.from('insights').insert(frameworksToInsert);
    }

    // Insert books
    if (extracted.books.length > 0) {
      await serverClient.from('books').delete().eq('episode_id', episode.id);
      await serverClient.from('books').insert(
        extracted.books.map(book => ({
          episode_id: episode.id,
          title: book.title,
          author: book.author,
          context: book.context,
          timestamp_seconds: book.timestamp,
        }))
      );
    }

    // Insert papers
    if (extracted.papers.length > 0) {
      await serverClient.from('papers').delete().eq('episode_id', episode.id);
      await serverClient.from('papers').insert(
        extracted.papers.map(paper => ({
          episode_id: episode.id,
          title: paper.title,
          authors: paper.authors,
          url: paper.url,
          context: paper.context,
          timestamp_seconds: paper.timestamp,
        }))
      );
    }

    // Store guest info (with channel_id)
    if (guests.length > 0) {
      for (const guest of guests) {
        const slug = guest.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
        
        // Check if guest already exists for this channel
        const { data: existingGuest } = await serverClient
          .from('guests')
          .select('id')
          .eq('channel_id', channel.id)
          .eq('slug', slug)
          .single();

        let guestId: string;

        if (existingGuest) {
          guestId = existingGuest.id;
        } else {
          const { data: newGuest, error: guestError } = await serverClient
            .from('guests')
            .insert({
              channel_id: channel.id,
              name: guest.name,
              slug: slug,
              bio: guest.role ? `${guest.role}${guest.company ? ` at ${guest.company}` : ''}` : null,
            })
            .select()
            .single();

          if (guestError) {
            console.warn(`  Warning: Could not create guest ${guest.name}: ${guestError.message}`);
            continue;
          }
          guestId = newGuest.id;
        }

        await serverClient
          .from('episode_guests')
          .upsert({ episode_id: episode.id, guest_id: guestId }, { onConflict: 'episode_id,guest_id' });
      }
    }

    console.log('  ✓ Stored in Supabase');

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
    .option('-l, --limit <number>', 'Maximum number of videos to process', parseInt)
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
    'NEXT_PUBLIC_SUPABASE_URL',
    'SUPABASE_SERVICE_ROLE_KEY',
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
  const serverClient = createServerClient();
  await initializeIndexes();

  // Get or create channel
  const channel = await getOrCreateChannel(serverClient, youtubeChannelId);
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
    const limit = options.all ? undefined : (options.limit || 10);
    console.log(`Fetching ${limit ? `up to ${limit}` : 'all'} videos from channel...`);
    videos = await fetchAllChannelVideos(youtubeChannelId, limit);
  }

  console.log(`\nFound ${videos.length} videos to process\n`);

  // Filter out already processed
  if (options.skipExisting) {
    const { data: existingEpisodes } = await serverClient
      .from('episodes')
      .select('youtube_id')
      .eq('channel_id', channel.id)
      .not('processed_at', 'is', null);

    const existingIds = new Set(existingEpisodes?.map(e => e.youtube_id) || []);
    const originalCount = videos.length;
    videos = videos.filter(v => !existingIds.has(v.id));
    console.log(`Skipping ${originalCount - videos.length} already processed videos\n`);
  }

  // Filter based on local progress if resuming
  if (options.resume && progress.processedVideoIds.length > 0) {
    const progressIds = new Set(progress.processedVideoIds);
    videos = videos.filter(v => !progressIds.has(v.id));
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

    const success = await processVideo(video, channel, serverClient, {
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
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
  }

  // Update channel last_synced_at
  await serverClient
    .from('channels')
    .update({ last_synced_at: new Date().toISOString() })
    .eq('id', channel.id);

  // Summary
  console.log('\n=======================');
  console.log('📊 Ingestion Summary');
  console.log('=======================');
  console.log(`📺 Channel: ${channel.name}`);
  console.log(`✅ Successful: ${successCount}`);
  console.log(`❌ Failed: ${failCount}`);
  console.log(`📁 Total: ${videos.length}`);
}

main().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
