import { fetchAll } from '@/lib/db';
import { EpisodesList } from '@/components/episodes-list';

type EpisodeRow = {
  id: string;
  youtube_id: string;
  title: string | null;
  description: string | null;
  thumbnail_url: string | null;
  published_at: string | null;
  duration_seconds: number | null;
};

async function getEpisodes(channelSlug: string) {
  // Single JOIN through channels avoids the old two-step lookup
  // (fetch channel, then filter episodes by channel_id).
  return fetchAll<EpisodeRow>(
    `SELECT e.id, e.youtube_id, e.title, e.description,
            e.thumbnail_url, e.published_at, e.duration_seconds
       FROM episodes e
       JOIN channels c ON c.id = e.channel_id
      WHERE c.slug = $1
        AND e.processed_at IS NOT NULL
      ORDER BY e.published_at DESC NULLS LAST`,
    [channelSlug],
  );
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
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        <EpisodesList episodes={episodes as any} channelSlug={channel} />
      </div>
    </div>
  );
}
