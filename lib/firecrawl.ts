/**
 * Firecrawl API Client
 * 
 * Used for web search to hydrate guest profiles with additional information
 * from the web, similar to how Perplexity/Exa.ai work.
 */

const FIRECRAWL_API_KEY = process.env.FIRECRAWL_API_KEY!;
const FIRECRAWL_API_URL = 'https://api.firecrawl.dev/v2';

export interface FirecrawlSource {
  url: string;
  title: string;
  description?: string;
  content?: string;
  markdown?: string;
  publishedDate?: string;
  author?: string;
  image?: string;
  favicon?: string;
  siteName?: string;
}

export interface FirecrawlSearchResult {
  web: FirecrawlSource[];
  news?: {
    url: string;
    title: string;
    description?: string;
    publishedDate?: string;
    source?: string;
    image?: string;
  }[];
  images?: {
    url: string;
    title: string;
    thumbnail?: string;
    source?: string;
    width?: number;
    height?: number;
  }[];
}

/**
 * Search the web using Firecrawl
 */
export async function searchWeb(
  query: string,
  options: {
    limit?: number;
    sources?: ('web' | 'news' | 'images')[];
    scrapeContent?: boolean;
  } = {}
): Promise<FirecrawlSearchResult> {
  if (!FIRECRAWL_API_KEY) {
    throw new Error('FIRECRAWL_API_KEY is not set');
  }

  const response = await fetch(`${FIRECRAWL_API_URL}/search`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${FIRECRAWL_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      query,
      sources: options.sources || ['web'],
      limit: options.limit || 5,
      scrapeOptions: options.scrapeContent !== false ? {
        formats: ['markdown'],
        onlyMainContent: true,
        maxAge: 86400000 * 30, // 30 days cache
      } : undefined,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(`Firecrawl API error: ${errorData.error || response.statusText}`);
  }

  const result = await response.json();
  const data = result.data || {};

  return {
    web: (data.web || []).map((item: any) => ({
      url: item.url,
      title: item.title || item.url,
      description: item.description || item.snippet,
      content: item.content,
      markdown: item.markdown,
      publishedDate: item.publishedDate,
      author: item.author,
      image: item.ogImage || item.image || item.metadata?.ogImage,
      favicon: item.favicon,
      siteName: item.url ? new URL(item.url).hostname : undefined,
    })),
    news: (data.news || []).map((item: any) => ({
      url: item.url,
      title: item.title,
      description: item.snippet || item.description,
      publishedDate: item.date,
      source: item.source || (item.url ? new URL(item.url).hostname : undefined),
      image: item.imageUrl,
    })),
    images: (data.images || []).filter((item: any) => item.url && item.imageUrl).map((item: any) => ({
      url: item.url,
      title: item.title || 'Untitled',
      thumbnail: item.imageUrl,
      source: item.url ? new URL(item.url).hostname : undefined,
      width: item.imageWidth,
      height: item.imageHeight,
    })),
  };
}

/**
 * Scrape a single URL for content
 */
export async function scrapeUrl(
  url: string,
  options: {
    formats?: ('markdown' | 'html')[];
    onlyMainContent?: boolean;
  } = {}
): Promise<{
  url: string;
  title?: string;
  markdown?: string;
  html?: string;
  metadata?: Record<string, any>;
}> {
  if (!FIRECRAWL_API_KEY) {
    throw new Error('FIRECRAWL_API_KEY is not set');
  }

  const response = await fetch(`${FIRECRAWL_API_URL}/scrape`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${FIRECRAWL_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      url,
      formats: options.formats || ['markdown'],
      onlyMainContent: options.onlyMainContent !== false,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(`Firecrawl scrape error: ${errorData.error || response.statusText}`);
  }

  const result = await response.json();
  return {
    url,
    title: result.data?.metadata?.title,
    markdown: result.data?.markdown,
    html: result.data?.html,
    metadata: result.data?.metadata,
  };
}

/**
 * Research a topic by searching and synthesizing results
 */
export async function researchTopic(
  topic: string,
  options: {
    limit?: number;
    includeNews?: boolean;
  } = {}
): Promise<{
  sources: FirecrawlSource[];
  context: string;
}> {
  const searchResult = await searchWeb(topic, {
    limit: options.limit || 5,
    sources: options.includeNews ? ['web', 'news'] : ['web'],
    scrapeContent: true,
  });

  // Build context from sources
  const context = searchResult.web
    .map((source, index) => {
      const content = source.markdown || source.content || source.description || '';
      // Limit content length per source
      const truncatedContent = content.length > 3000 
        ? content.substring(0, 3000) + '...' 
        : content;
      return `[${index + 1}] ${source.title}\nURL: ${source.url}\n${truncatedContent}`;
    })
    .join('\n\n---\n\n');

  return {
    sources: searchResult.web,
    context,
  };
}
