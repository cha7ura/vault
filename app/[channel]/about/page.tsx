import { createServerClient } from '@/lib/supabase';
import { format } from 'date-fns';

async function getChannel(slug: string) {
  const supabase = createServerClient();
  const { data } = await supabase
    .from('channels')
    .select('*')
    .eq('slug', slug)
    .single();
  return data;
}

async function getStats(channelId: string) {
  const supabase = createServerClient();
  
  const [episodesResult, guestsResult, insightsResult, booksResult] = await Promise.all([
    supabase.from('episodes').select('id', { count: 'exact', head: true }).eq('channel_id', channelId),
    supabase.from('guests').select('id', { count: 'exact', head: true }).eq('channel_id', channelId),
    supabase.from('insights').select('id', { count: 'exact', head: true }),
    supabase.from('books').select('id', { count: 'exact', head: true }),
  ]);

  return {
    episodes: episodesResult.count || 0,
    guests: guestsResult.count || 0,
    insights: insightsResult.count || 0,
    books: booksResult.count || 0,
  };
}

export default async function AboutPage({
  params,
}: {
  params: { channel: string };
}) {
  const channel = await getChannel(params.channel);
  if (!channel) return null;

  const stats = await getStats(channel.id);

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="max-w-3xl mx-auto">
          <h1 className="text-3xl font-bold mb-6">About {channel.name}</h1>
          
          {channel.description && (
            <p className="text-muted-foreground mb-8">{channel.description}</p>
          )}

          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-12">
            <div className="bg-card border rounded-lg p-4 text-center">
              <div className="text-3xl font-bold text-primary">{stats.episodes}</div>
              <div className="text-sm text-muted-foreground">Episodes</div>
            </div>
            <div className="bg-card border rounded-lg p-4 text-center">
              <div className="text-3xl font-bold text-primary">{stats.guests}</div>
              <div className="text-sm text-muted-foreground">Guests</div>
            </div>
            <div className="bg-card border rounded-lg p-4 text-center">
              <div className="text-3xl font-bold text-primary">{stats.insights}</div>
              <div className="text-sm text-muted-foreground">Insights</div>
            </div>
            <div className="bg-card border rounded-lg p-4 text-center">
              <div className="text-3xl font-bold text-primary">{stats.books}</div>
              <div className="text-sm text-muted-foreground">Books</div>
            </div>
          </div>

          <div className="bg-card border rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">Powered by Vault</h2>
            <p className="text-muted-foreground mb-4">
              This vault uses AI to automatically extract insights from podcast episodes, 
              including frameworks, quotes, book recommendations, and more.
            </p>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li>• <strong>Transcription</strong>: Deepgram with speaker diarization</li>
              <li>• <strong>AI Extraction</strong>: OpenRouter (GPT-4o)</li>
              <li>• <strong>Search</strong>: Meilisearch + pgvector hybrid search</li>
              <li>• <strong>Guest Research</strong>: Firecrawl web search</li>
            </ul>
            
            {channel.last_synced_at && (
              <p className="text-xs text-muted-foreground mt-4">
                Last synced: {format(new Date(channel.last_synced_at), 'PPp')}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
