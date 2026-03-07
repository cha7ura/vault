import Link from 'next/link';
import Image from 'next/image';
import { Card } from '@/components/ui/card';
import { formatDistanceToNow } from 'date-fns';

interface Episode {
  id: string;
  youtube_id: string;
  title: string;
  description?: string;
  thumbnail_url?: string;
  published_at?: string;
  duration_seconds?: number;
}

interface EpisodeCardProps {
  episode: Episode;
  channelSlug?: string;
}

export function EpisodeCard({ episode, channelSlug }: EpisodeCardProps) {
  const durationMinutes = episode.duration_seconds
    ? Math.floor(episode.duration_seconds / 60)
    : null;

  const href = channelSlug
    ? `/${channelSlug}/episodes/${episode.youtube_id}`
    : `/episodes/${episode.youtube_id}`;

  const thumbnailUrl = episode.thumbnail_url
    || `https://img.youtube.com/vi/${episode.youtube_id}/hqdefault.jpg`;

  return (
    <Link href={href}>
      <Card className="overflow-hidden hover:shadow-lg transition-shadow group">
        <div className="relative w-full aspect-video">
          <Image
            src={thumbnailUrl}
            alt={episode.title}
            fill
            className="object-cover group-hover:scale-105 transition-transform duration-300"
          />
          {durationMinutes && (
            <span className="absolute bottom-2 right-2 bg-black/80 text-white text-xs px-2 py-1 rounded">
              {durationMinutes} min
            </span>
          )}
        </div>
        <div className="p-4">
          <h3 className="font-semibold line-clamp-2 mb-2 group-hover:text-primary transition-colors">
            {episode.title}
          </h3>
          {episode.published_at && (
            <span className="text-xs text-muted-foreground">
              {formatDistanceToNow(new Date(episode.published_at), {
                addSuffix: true,
              })}
            </span>
          )}
        </div>
      </Card>
    </Link>
  );
}
