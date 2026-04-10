import { fetchAll } from '@/lib/db';
import { InsightCard } from '@/components/insight-card';

type InsightJoinRow = {
  id: string;
  episode_id: string;
  guest_id: string | null;
  type: string;
  title: string | null;
  content: string;
  start_time_seconds: number | null;
  end_time_seconds: number | null;
  created_at: string | null;
  episode_title: string | null;
  [key: string]: unknown;
};

async function getFrameworks(channelSlug: string) {
  const rows = await fetchAll<InsightJoinRow>(
    `SELECT i.*, e.title AS episode_title
       FROM insights i
       JOIN episodes e ON e.id = i.episode_id
       JOIN channels c ON c.id = e.channel_id
      WHERE c.slug = $1
        AND i.type = 'framework'
      ORDER BY i.created_at DESC NULLS LAST`,
    [channelSlug],
  );

  return rows.map(({ episode_title, ...insight }) => ({
    ...insight,
    episodes: episode_title ? { title: episode_title } : null,
  }));
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
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                insight={framework as any}
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
