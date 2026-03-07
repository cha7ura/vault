import Link from 'next/link';
import { Card } from '@/components/ui/card';
import { Lightbulb, Quote, BookOpen, Brain, Heart, Sparkles } from 'lucide-react';

interface Insight {
  id: string;
  type: string;
  title: string;
  content: string;
  episode_id?: string;
  start_time_seconds?: number;
  episodes?: {
    id?: string;
    title?: string;
  };
}

interface InsightCardProps {
  insight: Insight;
  channelSlug?: string;
  compact?: boolean;
}

const typeIcons: Record<string, typeof Lightbulb> = {
  framework: Lightbulb,
  quote: Quote,
  story: BookOpen,
  mindset: Brain,
  health: Heart,
  relationship: Sparkles,
  insight: Lightbulb,
};

const typeColors: Record<string, string> = {
  framework: 'text-amber-500 bg-amber-500/10',
  quote: 'text-purple-500 bg-purple-500/10',
  story: 'text-blue-500 bg-blue-500/10',
  mindset: 'text-green-500 bg-green-500/10',
  health: 'text-red-500 bg-red-500/10',
  relationship: 'text-pink-500 bg-pink-500/10',
  insight: 'text-cyan-500 bg-cyan-500/10',
};

export function InsightCard({ insight, channelSlug, compact }: InsightCardProps) {
  const Icon = typeIcons[insight.type] || Lightbulb;
  const colorClass = typeColors[insight.type] || 'text-primary bg-primary/10';
  
  const timeString = insight.start_time_seconds
    ? `${Math.floor(insight.start_time_seconds / 60)}:${String(
        insight.start_time_seconds % 60
      ).padStart(2, '0')}`
    : null;

  const episodeId = insight.episode_id || insight.episodes?.id;
  const href = channelSlug && episodeId
    ? `/${channelSlug}/episodes/${episodeId}`
    : episodeId 
      ? `/episode/${episodeId}`
      : '#';

  if (compact) {
    return (
      <Link href={href}>
        <Card className="p-3 hover:shadow-md transition-shadow">
          <div className="flex items-start gap-3">
            <div className={`p-1.5 rounded ${colorClass}`}>
              <Icon className="h-4 w-4" />
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="font-medium text-sm line-clamp-1">{insight.title}</h4>
              <p className="text-xs text-muted-foreground line-clamp-2 mt-1">
                {insight.content}
              </p>
            </div>
          </div>
        </Card>
      </Link>
    );
  }

  return (
    <Link href={href}>
      <Card className="p-5 hover:shadow-lg transition-shadow group">
        <div className="flex items-start gap-4">
          <div className={`p-2 rounded-lg ${colorClass}`}>
            <Icon className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-medium text-muted-foreground uppercase">
                {insight.type}
              </span>
              {timeString && (
                <span className="text-xs text-muted-foreground">@ {timeString}</span>
              )}
            </div>
            <h3 className="font-semibold mb-2 group-hover:text-primary transition-colors">
              {insight.title}
            </h3>
            <p className="text-sm text-muted-foreground line-clamp-3">
              {insight.content}
            </p>
            {insight.episodes?.title && (
              <div className="mt-3 text-xs text-muted-foreground">
                From: {insight.episodes.title}
              </div>
            )}
          </div>
        </div>
      </Card>
    </Link>
  );
}
