import { createServerClient } from '@/lib/supabase';
import { InsightCard } from '@/components/insight-card';

async function getFrameworks(channelSlug: string) {
  const supabase = createServerClient();
  
  const { data: channel } = await supabase
    .from('channels')
    .select('id')
    .eq('slug', channelSlug)
    .single();
  
  if (!channel) return [];

  // Get episode IDs for this channel
  const { data: episodes } = await supabase
    .from('episodes')
    .select('id')
    .eq('channel_id', channel.id);
  
  if (!episodes || episodes.length === 0) return [];

  const { data } = await supabase
    .from('insights')
    .select('*, episodes(title)')
    .eq('type', 'framework')
    .in('episode_id', episodes.map(e => e.id))
    .order('created_at', { ascending: false });
  
  return data || [];
}

export default async function FrameworksPage({
  params,
}: {
  params: Promise<{ channel: string }>;
}) {
  const { channel } = await params;
  const frameworks = await getFrameworks(channel);

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Frameworks</h1>
          <p className="text-muted-foreground">
            Mental models and systematic approaches extracted from episodes
          </p>
        </div>

        {frameworks.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {frameworks.map((framework) => (
              <InsightCard 
                key={framework.id} 
                insight={framework}
                channelSlug={channel}
              />
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <p className="text-muted-foreground">No frameworks extracted yet.</p>
          </div>
        )}
      </div>
    </div>
  );
}
