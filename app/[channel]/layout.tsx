import { notFound } from 'next/navigation';
import { getChannelBySlug } from '@/lib/channel';
import { ChannelSidebar } from '@/components/channel-sidebar';

export async function generateMetadata({ params }: { params: Promise<{ channel: string }> }) {
  const { channel: channelSlug } = await params;
  const channel = await getChannelBySlug(channelSlug);
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
  params: Promise<{ channel: string }>;
}) {
  const { channel: channelSlug } = await params;
  const channel = await getChannelBySlug(channelSlug);

  if (!channel) {
    notFound();
  }

  return (
    <div className="flex min-h-screen">
      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
      <ChannelSidebar channel={channel as any} />
      <main className="flex-1 lg:ml-64">
        {children}
      </main>
    </div>
  );
}
