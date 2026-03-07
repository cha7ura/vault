import { createServerClient } from '@/lib/supabase';
import { ChatInterface } from '@/components/chat-interface';

async function getChannel(slug: string) {
  const supabase = createServerClient();
  const { data } = await supabase
    .from('channels')
    .select('*')
    .eq('slug', slug)
    .single();
  return data;
}

export default async function AskPage({
  params,
}: {
  params: { channel: string };
}) {
  const channel = await getChannel(params.channel);
  if (!channel) return null;

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="max-w-3xl mx-auto">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold mb-2">Ask about {channel.name}</h1>
            <p className="text-muted-foreground">
              Get AI-powered answers based on episode transcripts and insights
            </p>
          </div>

          <ChatInterface channelId={channel.id} channelName={channel.name} />
        </div>
      </div>
    </div>
  );
}
