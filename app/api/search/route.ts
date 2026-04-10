import { NextResponse } from 'next/server';
import { searchEpisodes } from '@/lib/meilisearch';
import { fetchOne, fetchAll, vecStr } from '@/lib/db';
import { embed } from '@/lib/openrouter';

// Used by the semantic branch below. `similarity` is cosine similarity
// (1 - cosine distance) computed inline from pgvector's `<=>` operator.
type SemanticEpisodeRow = {
  id: string;
  youtube_id: string;
  title: string | null;
  description: string | null;
  thumbnail_url: string | null;
  published_at: string | null;
  channel_id: string;
  similarity: number;
};

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get('q') || '';
  const channelId = searchParams.get('channel_id');
  const channelSlug = searchParams.get('channel');

  if (!query) {
    return NextResponse.json({ error: 'Query is required' }, { status: 400 });
  }

  try {
    // Resolve channel_id from slug if needed
    let resolvedChannelId: string | null = channelId;
    if (!resolvedChannelId && channelSlug) {
      const channel = await fetchOne<{ id: string }>(
        'SELECT id FROM channels WHERE slug=$1',
        [channelSlug],
      );
      resolvedChannelId = channel?.id ?? null;
    }

    // Hybrid search: Meilisearch (keyword) + pgvector (semantic)
    const [keywordResults, semanticResults] = await Promise.all([
      searchEpisodes(query, {
        channelId: resolvedChannelId || undefined,
        limit: 20,
      }),
      (async () => {
        const queryEmbedding = await embed(query);
        // Cosine distance (`<=>`) → similarity = 1 - distance.
        // Filter by threshold and optional channel; order by distance so
        // the planner can use the ivfflat index on `embedding`.
        return fetchAll<SemanticEpisodeRow>(
          `SELECT id, youtube_id, title, description, thumbnail_url,
                  published_at, channel_id,
                  1 - (embedding <=> $1::vector) AS similarity
             FROM episodes
            WHERE embedding IS NOT NULL
              AND ($2::uuid IS NULL OR channel_id = $2::uuid)
              AND 1 - (embedding <=> $1::vector) > $3
            ORDER BY embedding <=> $1::vector
            LIMIT $4`,
          [vecStr(queryEmbedding), resolvedChannelId, 0.5, 20],
        );
      })(),
    ]);

    // Merge and deduplicate results
    type MergedResult = {
      id: string;
      youtube_id?: string;
      title?: string | null;
      description?: string | null;
      thumbnail_url?: string | null;
      published_at?: string | null;
      channel_id?: string;
      channel_slug?: string;
      score: number;
      source: 'keyword' | 'semantic' | 'hybrid';
    };
    const resultMap = new Map<string, MergedResult>();

    // Add keyword results
    for (const hit of keywordResults.hits) {
      resultMap.set(hit.id, {
        id: hit.id,
        youtube_id: hit.youtube_id,
        title: hit.title,
        description: hit.description,
        thumbnail_url: hit.thumbnail_url,
        published_at: hit.published_at,
        channel_id: hit.channel_id,
        channel_slug: hit.channel_slug,
        score: hit._rankingScore || 0,
        source: 'keyword',
      });
    }

    // Add semantic results
    for (const result of semanticResults) {
      const existing = resultMap.get(result.id);
      if (existing) {
        existing.score = (existing.score + result.similarity) / 2;
        existing.source = 'hybrid';
      } else {
        resultMap.set(result.id, {
          id: result.id,
          youtube_id: result.youtube_id,
          title: result.title,
          description: result.description,
          thumbnail_url: result.thumbnail_url,
          published_at: result.published_at,
          channel_id: result.channel_id,
          score: result.similarity,
          source: 'semantic',
        });
      }
    }

    // Sort by score and return
    const results = Array.from(resultMap.values())
      .sort((a, b) => b.score - a.score)
      .slice(0, 20);

    return NextResponse.json({
      query,
      channel_id: resolvedChannelId,
      results,
      total: results.length,
    });
  } catch (error) {
    console.error('Search error:', error);
    return NextResponse.json({ error: 'Search failed' }, { status: 500 });
  }
}
