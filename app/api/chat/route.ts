import { NextResponse } from 'next/server';
import { embed } from '@/lib/openrouter';
import { supabase } from '@/lib/supabase';
import OpenAI from 'openai';

export async function POST(request: Request) {
  try {
    const { messages, query, channelId, channelName } = await request.json();

    if (!query && (!messages || messages.length === 0)) {
      return NextResponse.json({ error: 'Query is required' }, { status: 400 });
    }

    const userQuery = query || messages[messages.length - 1]?.content;

    // Semantic search for context (with optional channel filter)
    const queryEmbedding = await embed(userQuery);
    
    const { data: episodes } = await supabase.rpc('semantic_search_episodes', {
      query_embedding: queryEmbedding,
      p_channel_id: channelId || null,
      match_count: 5,
      match_threshold: 0.5,
    });

    const { data: insights } = await supabase.rpc('semantic_search_insights', {
      query_embedding: queryEmbedding,
      p_channel_id: channelId || null,
      match_count: 5,
      match_threshold: 0.5,
    });

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
        content: context
          ? `${userQuery}\n\nContext:\n${context}`
          : userQuery,
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
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ content })}\n\n`));
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
    return NextResponse.json(
      { error: 'Chat failed' },
      { status: 500 }
    );
  }
}
