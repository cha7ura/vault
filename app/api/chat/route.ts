import { NextResponse } from 'next/server';
import { embed } from '@/lib/openrouter';
import { fetchAll, vecStr } from '@/lib/db';
import OpenAI from 'openai';

type EpisodeHit = {
  id: string;
  title: string | null;
  description: string | null;
  similarity: number;
};
type InsightHit = {
  id: string;
  title: string | null;
  content: string;
  similarity: number;
};

export async function POST(request: Request) {
  try {
    const { messages, query, channelId, channelName } = await request.json();

    if (!query && (!messages || messages.length === 0)) {
      return NextResponse.json({ error: 'Query is required' }, { status: 400 });
    }

    const userQuery = query || messages[messages.length - 1]?.content;

    // Semantic search over episodes + insights (with optional channel filter).
    // Cosine distance (`<=>`) → similarity = 1 - distance.
    const queryEmbedding = await embed(userQuery);
    const queryVec = vecStr(queryEmbedding);

    const [episodes, insights] = await Promise.all([
      fetchAll<EpisodeHit>(
        `SELECT id, title, description,
                1 - (embedding <=> $1::vector) AS similarity
           FROM episodes
          WHERE embedding IS NOT NULL
            AND ($2::uuid IS NULL OR channel_id = $2::uuid)
            AND 1 - (embedding <=> $1::vector) > $3
          ORDER BY embedding <=> $1::vector
          LIMIT $4`,
        [queryVec, channelId || null, 0.5, 5],
      ),
      // Insights don't have a direct channel_id; join through episodes
      // so the optional channel filter still works.
      fetchAll<InsightHit>(
        `SELECT i.id, i.title, i.content,
                1 - (i.embedding <=> $1::vector) AS similarity
           FROM insights i
           JOIN episodes e ON e.id = i.episode_id
          WHERE i.embedding IS NOT NULL
            AND ($2::uuid IS NULL OR e.channel_id = $2::uuid)
            AND 1 - (i.embedding <=> $1::vector) > $3
          ORDER BY i.embedding <=> $1::vector
          LIMIT $4`,
        [queryVec, channelId || null, 0.5, 5],
      ),
    ]);

    // Build context from search results
    let context = '';
    if (episodes && episodes.length > 0) {
      context += 'Relevant Episodes:\n';
      for (const episode of episodes.slice(0, 3)) {
        context += `- ${episode.title}: ${episode.description?.substring(0, 200)}\n`;
      }
    }
    if (insights && insights.length > 0) {
      context += '\nRelevant Insights:\n';
      for (const insight of insights.slice(0, 3)) {
        context += `- ${insight.title}: ${insight.content.substring(0, 200)}\n`;
      }
    }

    // Build system message based on channel context
    const channelContext = channelName
      ? `You are a helpful assistant for the "${channelName}" channel vault.`
      : 'You are a helpful assistant for this YouTube channel vault.';

    const systemMessage = `${channelContext}
Answer questions about episodes, guests, insights, frameworks, and more based on the provided context.
Be concise and helpful. If you don't know something, say so.
Always cite which episode your information comes from when possible.`;

    const chatMessages = [
      { role: 'system' as const, content: systemMessage },
      ...(messages || []).slice(-10),
      {
        role: 'user' as const,
        content: context ? `${userQuery}\n\nContext:\n${context}` : userQuery,
      },
    ];

    // Stream response using OpenAI SDK
    const openrouter = new OpenAI({
      baseURL: 'https://openrouter.ai/api/v1',
      apiKey: process.env.OPENROUTER_API_KEY!,
    });

    const stream = await openrouter.chat.completions.create({
      model: 'openai/gpt-4o',
      messages: chatMessages,
      temperature: 0.7,
      stream: true,
    });

    // Convert to ReadableStream
    const encoder = new TextEncoder();
    const readable = new ReadableStream({
      async start(controller) {
        for await (const chunk of stream) {
          const content = chunk.choices[0]?.delta?.content || '';
          if (content) {
            controller.enqueue(
              encoder.encode(`data: ${JSON.stringify({ content })}\n\n`),
            );
          }
        }
        controller.close();
      },
    });

    return new Response(readable, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      },
    });
  } catch (error) {
    console.error('Chat error:', error);
    return NextResponse.json({ error: 'Chat failed' }, { status: 500 });
  }
}
