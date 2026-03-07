import { fetchChannelVideos, parseDuration } from '@/lib/youtube';
import { transcribeAudio, formatTranscriptWithSpeakers } from './transcribe';
import { extractAllContent } from './extract-insights';
import { embed, embedBatch } from '@/lib/openrouter';
import { supabase, createServerClient } from '@/lib/supabase';
import { meilisearch, INDEXES, initializeIndexes } from '@/lib/meilisearch';

/**
 * Extract URLs from text (for references)
 */
function extractUrlsFromText(text: string): string[] {
  const urlRegex = /(https?:\/\/[^\s]+)/g;
  return text.match(urlRegex) || [];
}

/**
 * Main ingestion pipeline
 */
export async function ingestEpisodes() {
  console.log('Starting episode ingestion...');

  // Initialize Meilisearch indexes
  await initializeIndexes();

  // Fetch videos from YouTube
  console.log('Fetching videos from YouTube...');
  const { videos } = await fetchChannelVideos(50);

  const serverClient = createServerClient();

  for (const video of videos) {
    try {
      // Check if episode already exists
      const { data: existing } = await serverClient
        .from('episodes')
        .select('id, processed_at')
        .eq('youtube_id', video.id)
        .single();

      if (existing?.processed_at) {
        console.log(`Skipping ${video.id} - already processed`);
        continue;
      }

      console.log(`Processing ${video.id}: ${video.title}`);

      // Step 1: Download audio (this would be done with yt-dlp in production)
      // For now, we'll assume audio is available or use YouTube's audio URL
      const audioUrl = `https://www.youtube.com/watch?v=${video.id}`;
      // In production, use yt-dlp to download and upload to storage

      // Step 2: Transcribe
      console.log('Transcribing...');
      const transcript = await transcribeAudio(audioUrl, {
        diarize: true,
      });

      // Step 3: Extract insights
      console.log('Extracting insights...');
      const extracted = await extractAllContent(
        transcript.text,
        video.description
      );

      // Step 4: Generate embeddings
      console.log('Generating embeddings...');
      const [episodeEmbedding, insightEmbeddings] = await Promise.all([
        embed(video.title + ' ' + video.description + ' ' + transcript.text.substring(0, 5000)),
        embedBatch(extracted.insights.map(i => i.title + ' ' + i.content)),
      ]);

      // Step 5: Store in Supabase
      console.log('Storing in database...');
      const durationSeconds = parseDuration(video.duration);

      // Insert episode
      const { data: episode, error: episodeError } = await serverClient
        .from('episodes')
        .insert({
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
        })
        .select()
        .single();

      if (episodeError) {
        console.error('Error inserting episode:', episodeError);
        continue;
      }

      // Insert insights
      if (extracted.insights.length > 0) {
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

      // Step 6: Index in Meilisearch
      console.log('Indexing in Meilisearch...');
      await meilisearch.index(INDEXES.episodes).addDocuments([
        {
          id: episode.id,
          youtube_id: video.id,
          title: video.title,
          description: video.description,
          thumbnail_url: video.thumbnailUrl,
          published_at: video.publishedAt,
          duration_seconds: durationSeconds,
        },
      ]);

      console.log(`✓ Completed ${video.id}`);
    } catch (error) {
      console.error(`Error processing ${video.id}:`, error);
      continue;
    }
  }

  console.log('Ingestion complete!');
}

// Run if called directly
if (require.main === module) {
  ingestEpisodes().catch(console.error);
}
