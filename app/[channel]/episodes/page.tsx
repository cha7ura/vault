import { createServerClient } from '@/lib/supabase';
import { EpisodesList } from '@/components/episodes-list';

async function getEpisodes(channelSlug: string) {
  const supabase = createServerClient();

  const { data: channel } = await supabase
    .from('channels')
    .select('id')
    .eq('slug', channelSlug)
    .single();

  if (!channel) return [];

  const { data } = await supabase
    .from('episodes')
    .select('id, youtube_id, title, description, thumbnail_url, published_at, duration_seconds')
    .eq('channel_id', channel.id)
    .not('processed_at', 'is', null)
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
        </div>
        <EpisodesList episodes={episodes} channelSlug={channel} />
      </div>
    </div>
  );
}
