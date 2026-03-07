import { createServerClient } from '@/lib/supabase';
import { searchEpisodes, searchInsights } from '@/lib/meilisearch';
import { EpisodeCard } from '@/components/episode-card';
import { InsightCard } from '@/components/insight-card';
import { SearchComponent } from '@/components/search-bar';

interface SearchPageProps {
  params: { channel: string };
  searchParams: { q?: string };
}

async function getChannelId(slug: string) {
  const supabase = createServerClient();
  const { data } = await supabase
    .from('channels')
    .select('id, name')
    .eq('slug', slug)
    .single();
  return data;
}

export default async function SearchPage({ params, searchParams }: SearchPageProps) {
  const query = searchParams.q || '';
  const channel = await getChannelId(params.channel);
  
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
          <SearchComponent channelSlug={params.channel} />
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
                      channelSlug={params.channel}
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
                      channelSlug={params.channel}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* No Results */}
            {episodeResults.length === 0 && insightResults.length === 0 && (
              <div className="text-center py-12">
                <p className="text-muted-foreground">
                  No results found for "{query}"
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
