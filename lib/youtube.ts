/**
 * YouTube API Client
 * 
 * Multi-tenant: Works with any YouTube channel
 */

const YOUTUBE_API_KEY = process.env.YOUTUBE_API_KEY!;

export interface YouTubeVideo {
  id: string;
  title: string;
  description: string;
  thumbnailUrl: string;
  publishedAt: string;
  duration: string; // ISO 8601 duration
  channelId: string;
  channelTitle: string;
}

export interface YouTubeChannel {
  id: string;
  title: string;
  description: string;
  customUrl?: string; // e.g., @TheDiaryOfACEO
  thumbnailUrl: string;
  bannerUrl?: string;
  subscriberCount?: number;
  videoCount?: number;
}

/**
 * Extract channel ID from various YouTube URL formats
 * Supports:
 * - https://www.youtube.com/channel/UCrPseYLGpNygVi34QpGNqpA
 * - https://www.youtube.com/@TheDiaryOfACEO
 * - https://www.youtube.com/c/ChannelName
 * - UCrPseYLGpNygVi34QpGNqpA (direct ID)
 */
export async function resolveChannelId(input: string): Promise<string> {
  // Already a channel ID (starts with UC)
  if (input.startsWith('UC') && input.length === 24) {
    return input;
  }

  // Extract from URL
  let identifier: string | null = null;

  if (input.includes('youtube.com/channel/')) {
    const match = input.match(/youtube\.com\/channel\/([^/?]+)/);
    if (match) return match[1];
  }

  if (input.includes('youtube.com/@')) {
    const match = input.match(/youtube\.com\/@([^/?]+)/);
    if (match) identifier = `@${match[1]}`;
  }

  if (input.includes('youtube.com/c/')) {
    const match = input.match(/youtube\.com\/c\/([^/?]+)/);
    if (match) identifier = match[1];
  }

  // Handle @username format directly
  if (input.startsWith('@')) {
    identifier = input;
  }

  // If we have a handle/username, resolve it via API
  if (identifier) {
    const url = new URL('https://www.googleapis.com/youtube/v3/channels');
    url.searchParams.set('key', YOUTUBE_API_KEY);
    url.searchParams.set('forHandle', identifier.replace('@', ''));
    url.searchParams.set('part', 'id');

    const response = await fetch(url.toString());
    if (!response.ok) {
      throw new Error(`Failed to resolve channel: ${response.statusText}`);
    }

    const data = await response.json();
    if (data.items?.length > 0) {
      return data.items[0].id;
    }

    // Try with forUsername as fallback
    url.searchParams.delete('forHandle');
    url.searchParams.set('forUsername', identifier.replace('@', ''));
    
    const fallbackResponse = await fetch(url.toString());
    const fallbackData = await fallbackResponse.json();
    if (fallbackData.items?.length > 0) {
      return fallbackData.items[0].id;
    }

    throw new Error(`Could not resolve channel: ${identifier}`);
  }

  throw new Error(`Invalid YouTube channel URL or ID: ${input}`);
}

/**
 * Get channel information
 */
export async function getChannelInfo(channelId: string): Promise<YouTubeChannel> {
  const url = new URL('https://www.googleapis.com/youtube/v3/channels');
  url.searchParams.set('key', YOUTUBE_API_KEY);
  url.searchParams.set('id', channelId);
  url.searchParams.set('part', 'snippet,statistics,brandingSettings');

  const response = await fetch(url.toString());
  if (!response.ok) {
    throw new Error(`YouTube API error: ${response.statusText}`);
  }

  const data = await response.json();
  if (data.items?.length === 0) {
    throw new Error(`Channel not found: ${channelId}`);
  }

  const item = data.items[0];
  return {
    id: item.id,
    title: item.snippet.title,
    description: item.snippet.description,
    customUrl: item.snippet.customUrl,
    thumbnailUrl: item.snippet.thumbnails.high?.url || item.snippet.thumbnails.default?.url,
    bannerUrl: item.brandingSettings?.image?.bannerExternalUrl,
    subscriberCount: parseInt(item.statistics?.subscriberCount || '0', 10),
    videoCount: parseInt(item.statistics?.videoCount || '0', 10),
  };
}

/**
 * Fetch videos from a channel
 */
export async function fetchChannelVideos(
  channelId: string,
  maxResults: number = 50,
  pageToken?: string
): Promise<{ videos: YouTubeVideo[]; nextPageToken?: string }> {
  const url = new URL('https://www.googleapis.com/youtube/v3/search');
  url.searchParams.set('key', YOUTUBE_API_KEY);
  url.searchParams.set('channelId', channelId);
  url.searchParams.set('part', 'snippet');
  url.searchParams.set('order', 'date');
  url.searchParams.set('type', 'video');
  url.searchParams.set('maxResults', maxResults.toString());
  if (pageToken) {
    url.searchParams.set('pageToken', pageToken);
  }

  const response = await fetch(url.toString());
  if (!response.ok) {
    throw new Error(`YouTube API error: ${response.statusText}`);
  }

  const data = await response.json();

  if (!data.items || data.items.length === 0) {
    return { videos: [], nextPageToken: undefined };
  }

  // Fetch video details (duration) separately
  const videoIds = data.items.map((item: any) => item.id.videoId).join(',');
  const detailsUrl = new URL('https://www.googleapis.com/youtube/v3/videos');
  detailsUrl.searchParams.set('key', YOUTUBE_API_KEY);
  detailsUrl.searchParams.set('id', videoIds);
  detailsUrl.searchParams.set('part', 'contentDetails,snippet');

  const detailsResponse = await fetch(detailsUrl.toString());
  const detailsData = await detailsResponse.json();

  const videos: YouTubeVideo[] = detailsData.items.map((item: any) => ({
    id: item.id,
    title: item.snippet.title,
    description: item.snippet.description,
    thumbnailUrl: item.snippet.thumbnails.high?.url || item.snippet.thumbnails.default.url,
    publishedAt: item.snippet.publishedAt,
    duration: item.contentDetails.duration,
    channelId: item.snippet.channelId,
    channelTitle: item.snippet.channelTitle,
  }));

  return {
    videos,
    nextPageToken: data.nextPageToken,
  };
}

/**
 * Parse ISO 8601 duration to seconds
 */
export function parseDuration(duration: string): number {
  const match = duration.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
  if (!match) return 0;

  const hours = parseInt(match[1] || '0', 10);
  const minutes = parseInt(match[2] || '0', 10);
  const seconds = parseInt(match[3] || '0', 10);

  return hours * 3600 + minutes * 60 + seconds;
}

/**
 * Get video by ID
 */
export async function getVideoById(videoId: string): Promise<YouTubeVideo | null> {
  const url = new URL('https://www.googleapis.com/youtube/v3/videos');
  url.searchParams.set('key', YOUTUBE_API_KEY);
  url.searchParams.set('id', videoId);
  url.searchParams.set('part', 'contentDetails,snippet');

  const response = await fetch(url.toString());
  if (!response.ok) {
    return null;
  }

  const data = await response.json();
  if (data.items.length === 0) {
    return null;
  }

  const item = data.items[0];
  return {
    id: item.id,
    title: item.snippet.title,
    description: item.snippet.description,
    thumbnailUrl: item.snippet.thumbnails.high?.url || item.snippet.thumbnails.default.url,
    publishedAt: item.snippet.publishedAt,
    duration: item.contentDetails.duration,
    channelId: item.snippet.channelId,
    channelTitle: item.snippet.channelTitle,
  };
}

/**
 * Fetch all videos from a channel (paginated)
 */
export async function fetchAllChannelVideos(
  channelId: string,
  limit?: number
): Promise<YouTubeVideo[]> {
  const allVideos: YouTubeVideo[] = [];
  let pageToken: string | undefined;

  do {
    const { videos, nextPageToken } = await fetchChannelVideos(channelId, 50, pageToken);
    allVideos.push(...videos);
    pageToken = nextPageToken;

    if (limit && allVideos.length >= limit) {
      return allVideos.slice(0, limit);
    }
  } while (pageToken);

  return allVideos;
}

/**
 * Generate a URL-safe slug from channel name
 */
export function generateChannelSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
}
