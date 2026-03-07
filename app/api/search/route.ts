import { NextResponse } from 'next/server';
import { searchEpisodes, searchInsights } from '@/lib/meilisearch';
import { supabase } from '@/lib/supabase';
import { embed } from '@/lib/openrouter';

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
    let resolvedChannelId = channelId;
    if (!resolvedChannelId && channelSlug) {
      const { data: channel } = await supabase
        .from('channels')
        .select('id')
        .eq('slug', channelSlug)
        .single();
      resolvedChannelId = channel?.id;
    }

    // Hybrid search: Meilisearch (keyword) + pgvector (semantic)
    const [keywordResults, semanticResults] = await Promise.all([
      // Meilisearch keyword search
      searchEpisodes(query, { 
        channelId: resolvedChannelId || undefined,
        limit: 20 
      }),
      // Semantic search via Supabase
      (async () => {
        const queryEmbedding = await embed(query);
        const { data, error } = await supabase.rpc('semantic_search_episodes', {
          query_embedding: queryEmbedding,
          p_channel_id: resolvedChannelId || null,
          match_count: 20,
          match_threshold: 0.5,
        });
        if (error) throw error;
        return data || [];
      })(),
    ]);

    // Merge and deduplicate results
    const resultMap = new Map();

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
          ...result,
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
    return NextResponse.json(
      { error: 'Search failed' },
      { status: 500 }
    );
  }
}
