import { createServerClient } from '@/lib/supabase';
import { InsightCard } from '@/components/insight-card';

async function getQuotes(channelSlug: string) {
  const supabase = createServerClient();
  
  const { data: channel } = await supabase
    .from('channels')
    .select('id')
    .eq('slug', channelSlug)
    .single();
  
  if (!channel) return [];

  const { data: episodes } = await supabase
    .from('episodes')
    .select('id')
    .eq('channel_id', channel.id);
  
  if (!episodes || episodes.length === 0) return [];

  const { data } = await supabase
    .from('insights')
    .select('*, episodes(title)')
    .eq('type', 'quote')
    .in('episode_id', episodes.map(e => e.id))
    .order('created_at', { ascending: false });
  
  return data || [];
}

export default async function QuotesPage({
  params,
}: {
  params: { channel: string };
}) {
  const quotes = await getQuotes(params.channel);

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Quotes</h1>
          <p className="text-muted-foreground">
            Memorable quotes and statements from episodes
          </p>
        </div>

        {quotes.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {quotes.map((quote) => (
              <InsightCard 
                key={quote.id} 
                insight={quote}
                channelSlug={params.channel}
              />
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <p className="text-muted-foreground">No quotes extracted yet.</p>
          </div>
        )}
      </div>
    </div>
  );
}
