import OpenAI from 'openai';

export const openrouter = new OpenAI({
  baseURL: 'https://openrouter.ai/api/v1',
  apiKey: process.env.OPENROUTER_API_KEY!,
  defaultHeaders: {
    'HTTP-Referer': process.env.NEXT_PUBLIC_SITE_URL || 'https://doac-vault.vercel.app',
    'X-Title': 'DOAC Vault',
  },
});

// LLM chat completion
export async function chat(
  messages: OpenAI.Chat.Completions.ChatCompletionMessageParam[],
  model: string = 'openai/gpt-4o',
  options?: {
    temperature?: number;
    max_tokens?: number;
    stream?: boolean;
  }
) {
  return openrouter.chat.completions.create({
    model,
    messages,
    temperature: options?.temperature ?? 0.7,
    max_tokens: options?.max_tokens,
    stream: options?.stream ?? false,
  });
}

// Generate embeddings
export async function embed(text: string | string[]): Promise<number[]> {
  const response = await openrouter.embeddings.create({
    model: 'openai/text-embedding-3-small',
    input: Array.isArray(text) ? text : [text],
  });
  
  const embeddings = response.data.map(item => item.embedding);
  return Array.isArray(text) ? embeddings : embeddings[0];
}

// Batch embeddings for multiple texts
export async function embedBatch(texts: string[]): Promise<number[][]> {
  const response = await openrouter.embeddings.create({
    model: 'openai/text-embedding-3-small',
    input: texts,
  });
  
  return response.data.map(item => item.embedding);
}
