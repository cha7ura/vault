import { fetchChannelVideos, parseDuration } from '@/lib/youtube';
import { transcribeAudio } from './transcribe';
import { extractAllContent } from './extract-insights';
import { embed, embedBatch } from '@/lib/openrouter';
import {
  fetchOne,
  execute,
  executeReturning,
  vecStr,
} from '@/lib/db';
import { meilisearch, INDEXES, initializeIndexes } from '@/lib/meilisearch';

type EpisodeRow = { id: string };

/**
 * Extract URLs from text (for references)
 */
function extractUrlsFromText(text: string): string[] {
  const urlRegex = /(https?:\/\/[^\s]+)/g;
  return text.match(urlRegex) || [];
}

/**
 * Build a multi-row INSERT with positional placeholders. `casts` allows
 * per-column type coercion (e.g. `{ 5: 'vector' }` for pgvector embeddings).
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

  return {
    sql: `INSERT INTO ${table} (${colList}) VALUES ${placeholders.join(', ')}`,
    params,
  };
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

  for (const video of videos) {
    try {
      // Check if episode already exists
      const existing = await fetchOne<{ id: string; processed_at: string | null }>(
        `SELECT id, processed_at FROM episodes WHERE youtube_id = $1`,
        [video.id],
      );

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
        video.description,
      );

      // Step 4: Generate embeddings
      console.log('Generating embeddings...');
      const [episodeEmbedding, insightEmbeddings] = await Promise.all([
        embed(video.title + ' ' + video.description + ' ' + transcript.text.substring(0, 5000)),
        extracted.insights.length > 0
          ? embedBatch(extracted.insights.map(i => i.title + ' ' + i.content))
          : Promise.resolve([] as number[][]),
      ]);

      // Step 5: Store in database
      console.log('Storing in database...');
      const durationSeconds = parseDuration(video.duration);

      // Insert episode
      const episode = await executeReturning<EpisodeRow>(
        `INSERT INTO episodes
           (youtube_id, title, description, thumbnail_url,
            duration_seconds, published_at, transcript,
            transcript_formatted, embedding, "references", processed_at)
         VALUES
           ($1, $2, $3, $4, $5, $6, $7, $8, $9::vector, $10::jsonb, NOW())
         RETURNING id`,
        [
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
        console.error(`Error inserting episode ${video.id}`);
        continue;
      }

      // Insert insights
      if (extracted.insights.length > 0) {
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
          extracted.frameworks.map(f => f.title + ' ' + f.content),
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
        const rows = extracted.books.map(book => [
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
        const rows = extracted.papers.map(paper => [
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
