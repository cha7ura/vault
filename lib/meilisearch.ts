import { MeiliSearch } from 'meilisearch';

const meilisearchUrl = process.env.MEILISEARCH_URL || process.env.MEILISEARCH_HOST || 'http://localhost:7700';
const meilisearchKey = process.env.MEILISEARCH_MASTER_KEY || 'masterKey';

export const meilisearch = new MeiliSearch({
  host: meilisearchUrl,
  apiKey: meilisearchKey,
});

// Index names
export const INDEXES = {
  episodes: 'episodes',
  insights: 'insights',
  guests: 'guests',
  books: 'books',
  papers: 'papers',
  channels: 'channels',
} as const;

// Initialize indexes with settings (multi-tenant)
export async function initializeIndexes() {
  const client = meilisearch;

  // Channels index
  const channelsIndex = client.index(INDEXES.channels);
  await channelsIndex.updateSettings({
    searchableAttributes: ['name', 'description'],
    filterableAttributes: ['slug', 'youtube_channel_id'],
    sortableAttributes: ['name', 'subscriber_count', 'created_at'],
    displayedAttributes: ['id', 'youtube_channel_id', 'name', 'slug', 'description', 'thumbnail_url', 'subscriber_count', 'video_count'],
  });

  // Episodes index (with channel filtering)
  const episodesIndex = client.index(INDEXES.episodes);
  await episodesIndex.updateSettings({
    searchableAttributes: ['title', 'description', 'transcript'],
    filterableAttributes: ['channel_id', 'channel_slug', 'published_at'],
    sortableAttributes: ['published_at'],
    displayedAttributes: ['id', 'channel_id', 'channel_slug', 'youtube_id', 'title', 'description', 'thumbnail_url', 'published_at', 'duration_seconds'],
  });

  // Insights index (with channel filtering via episode)
  const insightsIndex = client.index(INDEXES.insights);
  await insightsIndex.updateSettings({
    searchableAttributes: ['title', 'content'],
    filterableAttributes: ['type', 'episode_id', 'guest_id', 'channel_id'],
    sortableAttributes: ['created_at'],
    displayedAttributes: ['id', 'type', 'title', 'content', 'episode_id', 'guest_id', 'channel_id', 'start_time_seconds'],
  });

  // Guests index (with channel filtering)
  const guestsIndex = client.index(INDEXES.guests);
  await guestsIndex.updateSettings({
    searchableAttributes: ['name', 'bio'],
    filterableAttributes: ['slug', 'channel_id'],
    sortableAttributes: ['name'],
    displayedAttributes: ['id', 'channel_id', 'name', 'slug', 'bio', 'photo_url', 'twitter', 'linkedin'],
  });

  // Books index
  const booksIndex = client.index(INDEXES.books);
  await booksIndex.updateSettings({
    searchableAttributes: ['title', 'author', 'context'],
    filterableAttributes: ['episode_id', 'channel_id'],
    sortableAttributes: ['timestamp_seconds'],
    displayedAttributes: ['id', 'title', 'author', 'amazon_url', 'episode_id', 'channel_id', 'context'],
  });

  // Papers index
  const papersIndex = client.index(INDEXES.papers);
  await papersIndex.updateSettings({
    searchableAttributes: ['title', 'authors', 'context'],
    filterableAttributes: ['episode_id', 'channel_id'],
    sortableAttributes: ['timestamp_seconds'],
    displayedAttributes: ['id', 'title', 'authors', 'url', 'episode_id', 'channel_id', 'context'],
  });
}

/**
 * Search episodes with channel filter
 */
export async function searchEpisodes(
  query: string,
  options: {
    channelId?: string;
    channelSlug?: string;
    limit?: number;
  } = {}
) {
  const filters: string[] = [];
  
  if (options.channelId) {
    filters.push(`channel_id = "${options.channelId}"`);
  }
  if (options.channelSlug) {
    filters.push(`channel_slug = "${options.channelSlug}"`);
  }

  return meilisearch.index(INDEXES.episodes).search(query, {
    limit: options.limit || 20,
    filter: filters.length > 0 ? filters.join(' AND ') : undefined,
  });
}

/**
 * Search insights with channel filter
 */
export async function searchInsights(
  query: string,
  options: {
    channelId?: string;
    type?: string;
    limit?: number;
  } = {}
) {
  const filters: string[] = [];
  
  if (options.channelId) {
    filters.push(`channel_id = "${options.channelId}"`);
  }
  if (options.type) {
    filters.push(`type = "${options.type}"`);
  }

  return meilisearch.index(INDEXES.insights).search(query, {
    limit: options.limit || 20,
    filter: filters.length > 0 ? filters.join(' AND ') : undefined,
  });
}

/**
 * Search guests with channel filter
 */
export async function searchGuests(
  query: string,
  options: {
    channelId?: string;
    limit?: number;
  } = {}
) {
  const filters: string[] = [];
  
  if (options.channelId) {
    filters.push(`channel_id = "${options.channelId}"`);
  }

  return meilisearch.index(INDEXES.guests).search(query, {
    limit: options.limit || 20,
    filter: filters.length > 0 ? filters.join(' AND ') : undefined,
  });
}
