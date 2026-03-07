import { createServerClient } from '@/lib/supabase';
import { SearchComponent } from '@/components/search-bar';

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
  
  const [episodes, guests, insights] = await Promise.all([
    supabase.from('episodes').select('id', { count: 'exact', head: true }).eq('channel_id', channelId),
    supabase.from('guests').select('id', { count: 'exact', head: true }).eq('channel_id', channelId),
    supabase.from('insights').select('id', { count: 'exact', head: true })
      .in('episode_id', 
        supabase.from('episodes').select('id').eq('channel_id', channelId)
      ),
  ]);

  return {
    episodes: episodes.count || 0,
    guests: guests.count || 0,
    insights: insights.count || 0,
  };
}

export default async function ChannelHomePage({
  params,
}: {
  params: Promise<{ channel: string }>;
}) {
  const { channel: channelSlug } = await params;
  const channel = await getChannel(channelSlug);
  if (!channel) return null;

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="text-center mb-12">
            <h1 className="text-4xl lg:text-5xl font-bold tracking-tight mb-4">
              Search {channel.name}
            </h1>
            <p className="text-lg text-muted-foreground">
              Explore episodes, insights, frameworks, and more
            </p>
          </div>
          
          <SearchComponent channelSlug={channelSlug} />
        </div>
      </div>
    </div>
  );
}
