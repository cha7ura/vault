import Link from 'next/link';
import { fetchAll } from '@/lib/db';
import { Play, Plus, ArrowRight } from 'lucide-react';

type ChannelRow = {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  thumbnail_url: string | null;
  video_count: number | null;
  subscriber_count: number | null;
};

async function getChannels() {
  return fetchAll<ChannelRow>(
    `SELECT id, slug, name, description, thumbnail_url,
            video_count, subscriber_count
       FROM channels
      ORDER BY name`,
  );
}

export default async function HomePage() {
  const channels = await getChannels();

  return (
    <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="max-w-5xl mx-auto">
          {/* Header */}
          <div className="text-center mb-16">
            <h1 className="text-5xl lg:text-6xl font-bold tracking-tight mb-4">
              Vault
            </h1>
            <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
              AI-powered search and insights for your favorite YouTube channels.
              Transcripts, frameworks, guest profiles, and more.
            </p>
          </div>

          {/* Channels Grid */}
          {channels.length > 0 ? (
            <div className="mb-16">
              <h2 className="text-2xl font-semibold mb-6">Your Channels</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {channels.map((channel) => (
                  <Link
                    key={channel.id}
                    href={`/${channel.slug}`}
                    className="group relative bg-card border border-border rounded-xl p-6 hover:border-primary/50 hover:shadow-lg transition-all"
                  >
                    <div className="flex items-start gap-4">
                      {channel.thumbnail_url ? (
                        <img
                          src={channel.thumbnail_url}
                          alt={channel.name}
                          className="w-16 h-16 rounded-lg object-cover"
                        />
                      ) : (
                        <div className="w-16 h-16 rounded-lg bg-primary/10 flex items-center justify-center">
                          <Play className="h-8 w-8 text-primary" />
                        </div>
                      )}
                      <div className="flex-1 min-w-0">
                        <h3 className="font-semibold text-lg truncate group-hover:text-primary transition-colors">
                          {channel.name}
                        </h3>
                        {channel.description && (
                          <p className="text-sm text-muted-foreground line-clamp-2 mt-1">
                            {channel.description}
                          </p>
                        )}
                        <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                          {channel.video_count && (
                            <span>{channel.video_count} videos</span>
                          )}
                          {channel.subscriber_count && (
                            <span>{(channel.subscriber_count / 1000000).toFixed(1)}M subs</span>
                          )}
                        </div>
                      </div>
                    </div>
                    <ArrowRight className="absolute top-6 right-6 h-5 w-5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                  </Link>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-center py-16 bg-card border border-dashed border-border rounded-xl mb-16">
              <Play className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium mb-2">No channels yet</h3>
              <p className="text-muted-foreground mb-6">
                Add your first YouTube channel to get started
              </p>
            </div>
          )}

          {/* Knowledge Graph */}
          <div className="mb-8">
            <Link
              href="/graph"
              className="group relative bg-card border border-border rounded-xl p-6 hover:border-primary/50 hover:shadow-lg transition-all flex items-center gap-4"
            >
              <div className="w-12 h-12 rounded-lg bg-purple-500/10 flex items-center justify-center shrink-0">
                <span className="text-2xl">🕸️</span>
              </div>
              <div>
                <h2 className="text-xl font-semibold group-hover:text-primary transition-colors">Knowledge Graph</h2>
                <p className="text-sm text-muted-foreground">
                  Explore entities, relationships, and observations extracted from episodes
                </p>
              </div>
              <ArrowRight className="ml-auto h-5 w-5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
            </Link>
          </div>

          {/* Add Channel Section */}
          <div className="bg-card border border-border rounded-xl p-8">
            <div className="flex items-start gap-6">
              <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                <Plus className="h-6 w-6 text-primary" />
              </div>
              <div className="flex-1">
                <h2 className="text-xl font-semibold mb-2">Add a Channel</h2>
                <p className="text-muted-foreground mb-4">
                  Use the CLI to ingest a new YouTube channel:
                </p>
                <div className="bg-muted/50 rounded-lg p-4 font-mono text-sm overflow-x-auto">
                  <code>npm run ingest -- --channel &quot;https://www.youtube.com/@YourChannel&quot; --limit 10</code>
                </div>
              </div>
            </div>
          </div>

          {/* Features */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-16">
            <div className="text-center p-6">
              <div className="w-12 h-12 rounded-lg bg-blue-500/10 flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">🎯</span>
              </div>
              <h3 className="font-semibold mb-2">AI Extraction</h3>
              <p className="text-sm text-muted-foreground">
                Automatically extract frameworks, insights, quotes, and book mentions
              </p>
            </div>
            <div className="text-center p-6">
              <div className="w-12 h-12 rounded-lg bg-purple-500/10 flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">🔍</span>
              </div>
              <h3 className="font-semibold mb-2">Hybrid Search</h3>
              <p className="text-sm text-muted-foreground">
                Full-text + semantic search across transcripts and insights
              </p>
            </div>
            <div className="text-center p-6">
              <div className="w-12 h-12 rounded-lg bg-green-500/10 flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">💬</span>
              </div>
              <h3 className="font-semibold mb-2">AI Chatbot</h3>
              <p className="text-sm text-muted-foreground">
                Ask questions and get answers grounded in episode content
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
