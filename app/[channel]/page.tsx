import { getChannelBySlug } from '@/lib/channel';
import { SearchComponent } from '@/components/search-bar';

export default async function ChannelHomePage({
  params,
}: {
  params: Promise<{ channel: string }>;
}) {
  const { channel: channelSlug } = await params;
  const channel = await getChannelBySlug(channelSlug);
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
