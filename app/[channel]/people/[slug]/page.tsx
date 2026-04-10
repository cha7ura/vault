import { fetchOne } from '@/lib/db';
import { parseJsonb } from '@/lib/db';
import { notFound } from 'next/navigation';
import Image from 'next/image';
import Link from 'next/link';

interface MemorySchema {
  persona?: {
    communication_style?: {
      tone?: string;
      formality?: string;
      storytelling_tendency?: string;
      signature_phrases?: string[];
      speech_patterns?: string[];
    };
    personality_traits?: Record<string, string>;
    expertise_domains?: { domain: string; depth: string }[];
  };
  semantic_memory?: {
    beliefs?: Record<string, { stance: string; confidence: string }>;
    frameworks?: {
      name: string;
      description: string;
      source_episode?: string;
    }[];
    recurring_themes?: string[];
    references?: {
      type: string;
      name: string;
      sentiment?: string;
      context?: string;
    }[];
    relationships?: { person: string; nature: string; context?: string }[];
  };
  episodic_memory?: {
    episode_id: string;
    date?: string;
    role: string;
    summary: string;
    key_moments?: string[];
    emotional_peaks?: { topic: string; reaction: string }[];
  }[];
  reflections?: {
    insight: string;
    importance: number;
    expert_lens?: string;
    derived_from?: string[];
  }[];
  contradictions?: {
    topic: string;
    earlier_stance: string;
    later_stance: string;
    resolution?: string;
  }[];
  growth_log?: {
    dimension: string;
    description: string;
    from_episode?: string;
    to_episode?: string;
  }[];
}

function Badge({
  children,
  variant = 'default',
}: {
  children: React.ReactNode;
  variant?: string;
}) {
  const colors: Record<string, string> = {
    default:
      'bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300',
    high: 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300',
    medium:
      'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300',
    low: 'bg-neutral-100 dark:bg-neutral-800 text-neutral-500',
    evolved:
      'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300',
    context_dependent:
      'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300',
    unresolved:
      'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300',
  };
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${colors[variant] || colors.default}`}
    >
      {children}
    </span>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-8">
      <h2 className="text-xl font-semibold mb-4 border-b border-neutral-200 dark:border-neutral-800 pb-2">
        {title}
      </h2>
      {children}
    </section>
  );
}

export default async function PersonPage({
  params,
}: {
  params: Promise<{ channel: string; slug: string }>;
}) {
  const { channel, slug } = await params;

  const person = await fetchOne<{
    id: string;
    name: string;
    slug: string;
    photo_url: string | null;
  }>(
    'SELECT id, name, slug, photo_url FROM people WHERE slug = $1',
    [slug],
  );

  if (!person) return notFound();

  const memRow = await fetchOne<{
    memory: unknown;
    memory_version: number;
    turns_processed: number | null;
    updated_at: string | null;
  }>(
    `SELECT memory, memory_version, turns_processed, updated_at
       FROM agent_memories
      WHERE person_id = $1`,
    [person.id],
  );

  if (!memRow) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12 text-center">
          <h1 className="text-2xl font-bold mb-4">{person.name}</h1>
          <p className="text-muted-foreground">
            No agent memory built yet. Run the pipeline first.
          </p>
          <Link
            href={`/${channel}/people`}
            className="text-sm text-blue-500 hover:underline mt-4 inline-block"
          >
            &larr; All People
          </Link>
        </div>
      </div>
    );
  }

  // JSONB is auto-decoded by node-postgres, but legacy rows may still be
  // double-encoded strings — parseJsonb() handles both shapes safely.
  const memory = (parseJsonb<MemorySchema>(memRow.memory) ?? {}) as MemorySchema;
  const persona = memory.persona;
  const semantic = memory.semantic_memory;

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12 max-w-4xl">
        {/* Header */}
        <div className="flex items-center gap-5 mb-8">
          {person.photo_url ? (
            <Image
              src={person.photo_url}
              alt={person.name}
              width={80}
              height={80}
              className="rounded-full object-cover"
            />
          ) : (
            <div className="w-20 h-20 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center text-2xl font-bold">
              {person.name.charAt(0)}
            </div>
          )}
          <div>
            <h1 className="text-3xl font-bold">{person.name}</h1>
            <p className="text-sm text-muted-foreground mt-1">
              {memRow.turns_processed} turns processed &middot; v
              {memRow.memory_version} &middot;{' '}
              {memory.episodic_memory?.length || 0} episodes
            </p>
          </div>
        </div>

        {/* Persona */}
        {persona && (
          <Section title="Persona">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {persona.communication_style && (
                <div>
                  <h3 className="text-sm font-semibold text-muted-foreground mb-2">
                    Communication Style
                  </h3>
                  <div className="space-y-1 text-sm">
                    {persona.communication_style.tone && (
                      <p>
                        Tone:{' '}
                        <Badge>{persona.communication_style.tone}</Badge>
                      </p>
                    )}
                    {persona.communication_style.formality && (
                      <p>
                        Formality:{' '}
                        <Badge>{persona.communication_style.formality}</Badge>
                      </p>
                    )}
                    {persona.communication_style.storytelling_tendency && (
                      <p>
                        Storytelling:{' '}
                        <Badge>
                          {persona.communication_style.storytelling_tendency}
                        </Badge>
                      </p>
                    )}
                  </div>
                  {persona.communication_style.signature_phrases &&
                    persona.communication_style.signature_phrases.length > 0 && (
                      <div className="mt-3">
                        <p className="text-xs text-muted-foreground mb-1">
                          Signature Phrases
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {persona.communication_style.signature_phrases.map(
                            (p, i) => (
                              <Badge key={i}>&ldquo;{p}&rdquo;</Badge>
                            )
                          )}
                        </div>
                      </div>
                    )}
                </div>
              )}

              {persona.personality_traits && (
                <div>
                  <h3 className="text-sm font-semibold text-muted-foreground mb-2">
                    Personality Traits (Big Five)
                  </h3>
                  <div className="space-y-1 text-sm">
                    {Object.entries(persona.personality_traits).map(
                      ([trait, level]) =>
                        level && (
                          <p key={trait} className="capitalize">
                            {trait.replace(/_/g, ' ')}:{' '}
                            <Badge variant={level}>{level}</Badge>
                          </p>
                        )
                    )}
                  </div>
                </div>
              )}
            </div>

            {persona.expertise_domains &&
              persona.expertise_domains.length > 0 && (
                <div className="mt-4">
                  <h3 className="text-sm font-semibold text-muted-foreground mb-2">
                    Expertise
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {persona.expertise_domains.map((d, i) => (
                      <Badge
                        key={i}
                        variant={
                          d.depth === 'deep'
                            ? 'high'
                            : d.depth === 'moderate'
                              ? 'medium'
                              : 'low'
                        }
                      >
                        {d.domain} ({d.depth})
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
          </Section>
        )}

        {/* Beliefs & Frameworks */}
        {semantic && (
          <Section title="Beliefs & Frameworks">
            {semantic.beliefs && Object.keys(semantic.beliefs).length > 0 && (
              <div className="mb-4">
                <h3 className="text-sm font-semibold text-muted-foreground mb-2">
                  Beliefs
                </h3>
                <div className="space-y-2">
                  {Object.entries(semantic.beliefs).map(([topic, belief]) => (
                    <div
                      key={topic}
                      className="border border-neutral-200 dark:border-neutral-800 rounded-lg p-3"
                    >
                      <p className="font-medium text-sm capitalize">
                        {topic.replace(/_/g, ' ')}
                      </p>
                      <p className="text-sm text-muted-foreground mt-1">
                        {belief.stance}
                      </p>
                      {belief.confidence && (
                        <Badge variant={belief.confidence}>
                          {belief.confidence} confidence
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {semantic.frameworks && semantic.frameworks.length > 0 && (
              <div className="mb-4">
                <h3 className="text-sm font-semibold text-muted-foreground mb-2">
                  Frameworks
                </h3>
                <div className="space-y-2">
                  {semantic.frameworks.map((fw, i) => (
                    <div
                      key={i}
                      className="border border-neutral-200 dark:border-neutral-800 rounded-lg p-3"
                    >
                      <p className="font-medium text-sm">{fw.name}</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        {fw.description}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {semantic.recurring_themes &&
              semantic.recurring_themes.length > 0 && (
                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-muted-foreground mb-2">
                    Recurring Themes
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {semantic.recurring_themes.map((theme, i) => (
                      <Badge key={i}>{theme}</Badge>
                    ))}
                  </div>
                </div>
              )}

            {semantic.relationships &&
              semantic.relationships.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-muted-foreground mb-2">
                    Relationships
                  </h3>
                  <div className="space-y-1">
                    {semantic.relationships.map((rel, i) => (
                      <p key={i} className="text-sm">
                        <span className="font-medium">{rel.person}</span>{' '}
                        <Badge>{rel.nature.replace(/_/g, ' ')}</Badge>
                        {rel.context && (
                          <span className="text-muted-foreground ml-1">
                            — {rel.context}
                          </span>
                        )}
                      </p>
                    ))}
                  </div>
                </div>
              )}
          </Section>
        )}

        {/* Reflections */}
        {memory.reflections && memory.reflections.length > 0 && (
          <Section title="Key Reflections">
            <div className="space-y-3">
              {memory.reflections
                .sort((a, b) => (b.importance || 0) - (a.importance || 0))
                .slice(0, 10)
                .map((ref, i) => (
                  <div key={i} className="border-l-2 border-blue-400 pl-3 py-1">
                    <p className="text-sm">{ref.insight}</p>
                    <div className="flex gap-2 mt-1">
                      {ref.expert_lens && <Badge>{ref.expert_lens}</Badge>}
                      <span className="text-xs text-muted-foreground">
                        importance: {(ref.importance * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                ))}
            </div>
          </Section>
        )}

        {/* Contradictions */}
        {memory.contradictions && memory.contradictions.length > 0 && (
          <Section title="Contradictions & Evolution">
            <div className="space-y-3">
              {memory.contradictions.map((c, i) => (
                <div
                  key={i}
                  className="border border-amber-200 dark:border-amber-800 rounded-lg p-3 bg-amber-50/50 dark:bg-amber-900/10"
                >
                  <p className="font-medium text-sm">{c.topic}</p>
                  <div className="grid grid-cols-2 gap-4 mt-2 text-sm">
                    <div>
                      <p className="text-xs text-muted-foreground">Earlier</p>
                      <p className="text-neutral-600 dark:text-neutral-400">
                        {c.earlier_stance}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Later</p>
                      <p className="text-neutral-600 dark:text-neutral-400">
                        {c.later_stance}
                      </p>
                    </div>
                  </div>
                  {c.resolution && (
                    <div className="mt-2">
                      <Badge variant={c.resolution}>{c.resolution}</Badge>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Growth Timeline */}
        {memory.growth_log && memory.growth_log.length > 0 && (
          <Section title="Growth Timeline">
            <div className="border-l-2 border-neutral-300 dark:border-neutral-700 ml-2 space-y-4">
              {memory.growth_log.map((entry, i) => (
                <div key={i} className="pl-4 relative">
                  <div className="absolute -left-[9px] top-1 w-4 h-4 rounded-full bg-blue-500 border-2 border-white dark:border-neutral-900" />
                  <p className="text-sm font-medium capitalize">
                    {entry.dimension.replace(/_/g, ' ')}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {entry.description}
                  </p>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Episode Appearances */}
        {memory.episodic_memory && memory.episodic_memory.length > 0 && (
          <Section title="Episode Appearances">
            <div className="space-y-3">
              {memory.episodic_memory.map((ep, i) => (
                <div
                  key={i}
                  className="border border-neutral-200 dark:border-neutral-800 rounded-lg p-3"
                >
                  <div className="flex justify-between items-start">
                    <p className="text-sm font-medium">{ep.summary}</p>
                    <Badge>{ep.role}</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {ep.date
                      ? new Date(ep.date).toLocaleDateString()
                      : 'Date unknown'}
                  </p>
                  {ep.key_moments && ep.key_moments.length > 0 && (
                    <div className="mt-2">
                      {ep.key_moments.map((m, j) => (
                        <p
                          key={j}
                          className="text-xs text-muted-foreground italic"
                        >
                          &ldquo;{m}&rdquo;
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Back link */}
        <div className="mt-8 pt-4 border-t border-neutral-200 dark:border-neutral-800">
          <Link
            href={`/${channel}/people`}
            className="text-sm text-blue-500 hover:underline"
          >
            &larr; All People
          </Link>
        </div>
      </div>
    </div>
  );
}
