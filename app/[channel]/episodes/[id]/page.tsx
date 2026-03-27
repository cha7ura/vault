import { notFound } from 'next/navigation';
import { createServerClient } from '@/lib/supabase';
import { EpisodeTranscriptTabs } from '@/components/episode-transcript-tabs';
import { format } from 'date-fns';
import { Clock, Calendar, ExternalLink, FileText, Lightbulb, BookOpen } from 'lucide-react';

async function getEpisode(youtubeId: string) {
  const supabase = createServerClient();
  const { data } = await supabase
    .from('episodes')
    .select('*')
    .eq('youtube_id', youtubeId)
    .single();
  return data;
}

async function getSegments(episodeId: string) {
  const supabase = createServerClient();
  const { data } = await supabase
    .from('segments')
    .select('id, start_time, end_time, text, speaker, words, diarizer')
    .eq('episode_id', episodeId)
    .order('start_time');
  return data || [];
}

function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function ComingSoonSection({ icon: Icon, title }: { icon: React.ComponentType<{ className?: string }>; title: string }) {
  return (
    <div className="border rounded-lg p-4 opacity-60">
      <div className="flex items-center gap-2 mb-3">
        <Icon className="h-4 w-4" />
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      <p className="text-xs text-muted-foreground">Coming soon</p>
    </div>
  );
}

export default async function EpisodePage({
  params,
}: {
  params: Promise<{ channel: string; id: string }>;
}) {
  const { channel, id } = await params;
  const episode = await getEpisode(id);

  if (!episode) {
    notFound();
  }

  const segments = await getSegments(episode.id);

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6 sm:py-10">
        {/* Header */}
        <div className="mb-6 sm:mb-8">
          <h1 className="text-xl sm:text-2xl lg:text-3xl font-bold mb-3">{episode.title}</h1>

          <div className="flex flex-wrap items-center gap-3 sm:gap-4 text-xs sm:text-sm text-muted-foreground mb-3">
            {episode.published_at && (
              <div className="flex items-center gap-1">
                <Calendar className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                {format(new Date(episode.published_at), 'MMM d, yyyy')}
              </div>
            )}
            {episode.duration_seconds && (
              <div className="flex items-center gap-1">
                <Clock className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                {formatDuration(episode.duration_seconds)}
              </div>
            )}
            <a
              href={`https://youtube.com/watch?v=${episode.youtube_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 hover:text-foreground"
            >
              <ExternalLink className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
              YouTube
            </a>
          </div>

          {episode.description && (
            <p className="text-muted-foreground text-xs sm:text-sm whitespace-pre-line line-clamp-3 sm:line-clamp-4 max-w-4xl">
              {episode.description}
            </p>
          )}
        </div>

        {/* Video — full width, sticky on desktop so it stays visible while scrolling transcript */}
        <div className="mb-6 sm:mb-8">
          <div className="aspect-video bg-muted rounded-lg overflow-hidden lg:sticky lg:top-4 lg:z-10">
            <iframe
              src={`https://www.youtube.com/embed/${episode.youtube_id}?enablejsapi=1&origin=${process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000'}`}
              title={episode.title}
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
              className="w-full h-full"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 lg:gap-8">
          {/* Transcript */}
          <div className="lg:col-span-2">
            {segments.length > 0 && (
              <EpisodeTranscriptTabs
                segments={segments}
                youtubeId={episode.youtube_id}
              />
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-4 order-first lg:order-last">
            <ComingSoonSection icon={FileText} title="Summary" />
            <ComingSoonSection icon={Lightbulb} title="Key Insights" />
            <ComingSoonSection icon={BookOpen} title="Books Mentioned" />
          </div>
        </div>
      </div>
    </div>
  );
}
