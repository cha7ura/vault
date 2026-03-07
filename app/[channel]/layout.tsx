import { notFound } from 'next/navigation';
import { createServerClient } from '@/lib/supabase';
import { ChannelSidebar } from '@/components/channel-sidebar';

async function getChannel(slug: string) {
  const supabase = createServerClient();
  const { data } = await supabase
    .from('channels')
    .select('*')
    .eq('slug', slug)
    .single();
  return data;
}

export async function generateMetadata({ params }: { params: { channel: string } }) {
  const channel = await getChannel(params.channel);
  if (!channel) return { title: 'Channel Not Found' };
  
  return {
    title: `${channel.name} | Vault`,
    description: channel.description || `Explore episodes, insights, and more from ${channel.name}`,
  };
}

export default async function ChannelLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { channel: string };
}) {
  const channel = await getChannel(params.channel);
  
  if (!channel) {
    notFound();
  }

  return (
    <div className="flex min-h-screen">
      <ChannelSidebar channel={channel} />
      <main className="flex-1 lg:ml-64">
        {children}
      </main>
    </div>
  );
}
