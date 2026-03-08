import { createServerClient } from '@/lib/supabase';
import { Users } from 'lucide-react';
import Image from 'next/image';
import Link from 'next/link';

export default async function PeoplePage({
  params,
}: {
  params: Promise<{ channel: string }>;
}) {
  const { channel } = await params;
  const supabase = createServerClient();

  // Get channel
  const { data: channelData } = await supabase
    .from('channels')
    .select('id, name')
    .eq('slug', channel)
    .single();

  if (!channelData) {
    return (
      <div className="p-8 text-center text-neutral-500">Channel not found</div>
    );
  }

  // Get all people who have agent memories
  const { data: memoryRows } = await supabase
    .from('agent_memories')
    .select(
      'person_id, memory_version, turns_processed, updated_at, people(id, name, slug, photo_url)'
    )
    .order('updated_at', { ascending: false });

  const peopleWithMemory = (memoryRows || [])
    .filter((row: any) => row.people)
    .map((row: any) => ({
      ...row.people,
      memory_version: row.memory_version,
      turns_processed: row.turns_processed,
      updated_at: row.updated_at,
    }));

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
            {peopleWithMemory.map((person: any) => (
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
