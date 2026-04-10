import { fetchOne } from '@/lib/db';
import { searchEpisodes, searchInsights } from '@/lib/meilisearch';
import { EpisodeCard } from '@/components/episode-card';
import { InsightCard } from '@/components/insight-card';
import { SearchComponent } from '@/components/search-bar';

interface SearchPageProps {
  params: Promise<{ channel: string }>;
  searchParams: Promise<{ q?: string }>;
}

type ChannelLite = { id: string; name: string };

async function getChannelId(slug: string) {
  return fetchOne<ChannelLite>(
    'SELECT id, name FROM channels WHERE slug = $1',
    [slug],
  );
}

export default async function SearchPage({ params, searchParams }: SearchPageProps) {
  const { channel: channelSlug } = await params;
  const { q: query = '' } = await searchParams;
  const channel = await getChannelId(channelSlug);

  if (!channel) return null;

  let episodeResults: any[] = [];
  let insightResults: any[] = [];

  if (query) {
    try {
      const [episodes, insights] = await Promise.all([
        searchEpisodes(query, { channelId: channel.id, limit: 10 }),
        searchInsights(query, { channelId: channel.id, limit: 10 }),
      ]);
      episodeResults = episodes.hits;
      insightResults = insights.hits;
    } catch (error) {
      console.error('Search error:', error);
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="max-w-4xl mx-auto mb-8">
          <SearchComponent channelSlug={channelSlug} />
        </div>

        {query && (
          <div className="space-y-12">
            {/* Episode Results */}
            {episodeResults.length > 0 && (
              <section>
                <h2 className="text-xl font-semibold mb-4">
                  Episodes ({episodeResults.length})
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {episodeResults.map((episode) => (
                    <EpisodeCard
                      key={episode.id}
                      episode={episode}
                      channelSlug={channelSlug}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Insight Results */}
            {insightResults.length > 0 && (
              <section>
                <h2 className="text-xl font-semibold mb-4">
                  Insights ({insightResults.length})
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {insightResults.map((insight) => (
                    <InsightCard
                      key={insight.id}
                      insight={insight}
                      channelSlug={channelSlug}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* No Results */}
            {episodeResults.length === 0 && insightResults.length === 0 && (
              <div className="text-center py-12">
                <p className="text-muted-foreground">
                  No results found for &ldquo;{query}&rdquo;
                </p>
              </div>
            )}
          </div>
        )}

        {!query && (
          <div className="text-center py-12">
            <p className="text-muted-foreground">
              Enter a search query to find episodes and insights
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
