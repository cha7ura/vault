import { notFound } from 'next/navigation';
import { createServerClient } from '@/lib/supabase';
import { TranscriptViewer } from '@/components/transcript-viewer';
import { InsightCard } from '@/components/insight-card';
import { BookCard } from '@/components/book-card';
import { format } from 'date-fns';
import { Clock, Calendar, ExternalLink } from 'lucide-react';

async function getEpisode(id: string) {
  const supabase = createServerClient();
  const { data } = await supabase
    .from('episodes')
    .select('*')
    .eq('id', id)
    .single();
  return data;
}

async function getEpisodeDetails(episodeId: string) {
  const supabase = createServerClient();

  const [insights, books, segments] = await Promise.all([
    supabase
      .from('insights')
      .select('*')
      .eq('episode_id', episodeId)
      .order('start_time_seconds'),
    supabase
      .from('books')
      .select('*')
      .eq('episode_id', episodeId),
    supabase
      .from('segments')
      .select('id, start_time, end_time, text, speaker, words')
      .eq('episode_id', episodeId)
      .order('start_time'),
  ]);

  return {
    insights: insights.data || [],
    books: books.data || [],
    segments: segments.data || [],
  };
}

function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}

export default async function EpisodePage({
  params,
}: {
  params: { channel: string; id: string };
}) {
  const episode = await getEpisode(params.id);
  
  if (!episode) {
    notFound();
  }

  const { insights, books, segments } = await getEpisodeDetails(params.id);

  const frameworks = insights.filter(i => i.type === 'framework');
  const otherInsights = insights.filter(i => i.type !== 'framework');

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {/* Header */}
        <div className="max-w-4xl mb-8">
          <h1 className="text-3xl font-bold mb-4">{episode.title}</h1>
          
          <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground mb-4">
            {episode.published_at && (
              <div className="flex items-center gap-1">
                <Calendar className="h-4 w-4" />
                {format(new Date(episode.published_at), 'MMM d, yyyy')}
              </div>
            )}
            {episode.duration_seconds && (
              <div className="flex items-center gap-1">
                <Clock className="h-4 w-4" />
                {formatDuration(episode.duration_seconds)}
              </div>
            )}
            <a
              href={`https://youtube.com/watch?v=${episode.youtube_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 hover:text-foreground"
            >
              <ExternalLink className="h-4 w-4" />
              Watch on YouTube
            </a>
          </div>

          {episode.description && (
            <p className="text-muted-foreground line-clamp-3">
              {episode.description}
            </p>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main Content */}
          <div className="lg:col-span-2 space-y-8">
            {/* Video Embed */}
            <div className="aspect-video bg-muted rounded-lg overflow-hidden">
              <iframe
                src={`https://www.youtube.com/embed/${episode.youtube_id}?enablejsapi=1`}
                title={episode.title}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                className="w-full h-full"
              />
            </div>

            {/* Transcript */}
            {(segments.length > 0 || episode.transcript) && (
              <div>
                <h2 className="text-xl font-semibold mb-4">Transcript</h2>
                {segments.length > 0 ? (
                  <TranscriptViewer
                    segments={segments}
                    youtubeId={episode.youtube_id}
                  />
                ) : (
                  <TranscriptViewer transcript={episode.transcript_formatted || episode.transcript} />
                )}
              </div>
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-8">
            {/* Frameworks */}
            {frameworks.length > 0 && (
              <div>
                <h2 className="text-lg font-semibold mb-4">Frameworks</h2>
                <div className="space-y-3">
                  {frameworks.map((framework) => (
                    <InsightCard key={framework.id} insight={framework} compact />
                  ))}
                </div>
              </div>
            )}

            {/* Key Insights */}
            {otherInsights.length > 0 && (
              <div>
                <h2 className="text-lg font-semibold mb-4">Key Insights</h2>
                <div className="space-y-3">
                  {otherInsights.slice(0, 5).map((insight) => (
                    <InsightCard key={insight.id} insight={insight} compact />
                  ))}
                </div>
              </div>
            )}

            {/* Books */}
            {books.length > 0 && (
              <div>
                <h2 className="text-lg font-semibold mb-4">Books Mentioned</h2>
                <div className="space-y-3">
                  {books.map((book) => (
                    <BookCard key={book.id} book={book} compact />
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
