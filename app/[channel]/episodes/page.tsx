import Link from 'next/link';
import { createServerClient } from '@/lib/supabase';
import { EpisodeCard } from '@/components/episode-card';

async function getEpisodes(channelSlug: string) {
  const supabase = createServerClient();
  
  // First get channel ID
  const { data: channel } = await supabase
    .from('channels')
    .select('id')
    .eq('slug', channelSlug)
    .single();
  
  if (!channel) return [];

  const { data } = await supabase
    .from('episodes')
    .select('*')
    .eq('channel_id', channel.id)
    .order('published_at', { ascending: false });
  
  return data || [];
}

export default async function EpisodesPage({
  params,
}: {
  params: Promise<{ channel: string }>;
}) {
  const { channel } = await params;
  const episodes = await getEpisodes(channel);

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Episodes</h1>
          <p className="text-muted-foreground">
            {episodes.length} episodes
          </p>
        </div>

        {episodes.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {episodes.map((episode) => (
              <EpisodeCard 
                key={episode.id} 
                episode={episode}
                channelSlug={channel}
              />
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <p className="text-muted-foreground">No episodes yet.</p>
          </div>
        )}
      </div>
    </div>
  );
}
