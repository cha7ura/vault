import { fetchOne, fetchAll } from '@/lib/db';
import { Users } from 'lucide-react';
import Image from 'next/image';
import Link from 'next/link';

type PersonWithMemory = {
  id: string;
  name: string;
  slug: string;
  photo_url: string | null;
  memory_version: number;
  turns_processed: number | null;
  updated_at: string | null;
};

export default async function PeoplePage({
  params,
}: {
  params: Promise<{ channel: string }>;
}) {
  const { channel } = await params;

  // Verify the channel exists so the sidebar / routing stays consistent.
  // agent_memories is a global table (no channel_id), so the list itself is
  // not filtered by channel — we're just gating the page on a valid slug.
  const channelData = await fetchOne<{ id: string; name: string }>(
    'SELECT id, name FROM channels WHERE slug = $1',
    [channel],
  );

  if (!channelData) {
    return (
      <div className="p-8 text-center text-neutral-500">Channel not found</div>
    );
  }

  // Flat JOIN replaces Supabase's FK expansion
  // `people(id, name, slug, photo_url)`.
  const peopleWithMemory = await fetchAll<PersonWithMemory>(
    `SELECT p.id, p.name, p.slug, p.photo_url,
            am.memory_version, am.turns_processed, am.updated_at
       FROM agent_memories am
       JOIN people p ON p.id = am.person_id
      ORDER BY am.updated_at DESC NULLS LAST`,
  );

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">People</h1>
          <p className="text-muted-foreground">
            AI-generated persona profiles built from podcast transcripts
          </p>
        </div>

        {peopleWithMemory.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
              <Users className="h-8 w-8 text-muted-foreground" />
            </div>
            <h2 className="text-xl font-semibold mb-2">No Agent Profiles Yet</h2>
            <p className="text-muted-foreground max-w-md">
              Run the people agents pipeline to build persona profiles from
              transcripts.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {peopleWithMemory.map((person) => (
              <Link
                key={person.id}
                href={`/${channel}/people/${person.slug}`}
                className="border border-neutral-200 dark:border-neutral-800 rounded-xl p-5 hover:border-neutral-400 dark:hover:border-neutral-600 transition-colors"
              >
                <div className="flex items-center gap-4 mb-3">
                  {person.photo_url ? (
                    <Image
                      src={person.photo_url}
                      alt={person.name}
                      width={48}
                      height={48}
                      className="rounded-full object-cover"
                    />
                  ) : (
                    <div className="w-12 h-12 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center text-lg font-semibold">
                      {person.name.charAt(0)}
                    </div>
                  )}
                  <div>
                    <h3 className="font-semibold">{person.name}</h3>
                    <p className="text-xs text-muted-foreground">
                      {person.turns_processed || 0} turns processed
                    </p>
                  </div>
                </div>
                <p className="text-sm text-muted-foreground">
                  v{person.memory_version} &middot; Updated{' '}
                  {person.updated_at
                    ? new Date(person.updated_at).toLocaleDateString()
                    : 'never'}
                </p>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
