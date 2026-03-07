'use client';

import { useState, useMemo } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { EpisodeCard } from '@/components/episode-card';
import { Search, LayoutGrid, List, ChevronDown, Users, Calendar } from 'lucide-react';
import { format } from 'date-fns';
import Image from 'next/image';
import Link from 'next/link';

interface Episode {
  id: string;
  youtube_id: string;
  title: string;
  description?: string;
  thumbnail_url?: string;
  published_at?: string;
  duration_seconds?: number;
}

type SortOption = 'newest' | 'oldest' | 'longest' | 'shortest';
type ViewMode = 'grid' | 'list';

interface EpisodesListProps {
  episodes: Episode[];
  channelSlug: string;
}

function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export function EpisodesList({ episodes, channelSlug }: EpisodesListProps) {
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortOption>('newest');
  const [view, setView] = useState<ViewMode>('grid');
  const [sortOpen, setSortOpen] = useState(false);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const sortLabels: Record<SortOption, string> = {
    newest: 'Newest first',
    oldest: 'Oldest first',
    longest: 'Longest',
    shortest: 'Shortest',
  };

  const filtered = useMemo(() => {
    let result = episodes;

    // Search by title
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(ep => ep.title.toLowerCase().includes(q));
    }

    // Date range filter
    if (dateFrom) {
      const from = new Date(dateFrom);
      result = result.filter(ep => ep.published_at && new Date(ep.published_at) >= from);
    }
    if (dateTo) {
      const to = new Date(dateTo);
      to.setMonth(to.getMonth() + 1);
      result = result.filter(ep => ep.published_at && new Date(ep.published_at) < to);
    }

    // Sort
    result = [...result].sort((a, b) => {
      switch (sort) {
        case 'newest':
          return (b.published_at || '').localeCompare(a.published_at || '');
        case 'oldest':
          return (a.published_at || '').localeCompare(b.published_at || '');
        case 'longest':
          return (b.duration_seconds || 0) - (a.duration_seconds || 0);
        case 'shortest':
          return (a.duration_seconds || 0) - (b.duration_seconds || 0);
      }
    });

    return result;
  }, [episodes, search, sort, dateFrom, dateTo]);

  return (
    <div>
      {/* Controls */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search episodes..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>

        {/* Sort dropdown */}
        <div className="relative">
          <Button
            variant="outline"
            onClick={() => setSortOpen(!sortOpen)}
            className="w-full sm:w-auto justify-between gap-2"
          >
            {sortLabels[sort]}
            <ChevronDown className="h-4 w-4" />
          </Button>
          {sortOpen && (
            <div className="absolute right-0 top-full mt-1 w-48 bg-popover border rounded-md shadow-md z-10">
              {(Object.entries(sortLabels) as [SortOption, string][]).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => { setSort(key); setSortOpen(false); }}
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-accent ${sort === key ? 'bg-accent font-medium' : ''}`}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* View toggle */}
        <div className="flex border rounded-md">
          <Button
            variant={view === 'grid' ? 'default' : 'ghost'}
            size="icon"
            onClick={() => setView('grid')}
            className="rounded-r-none"
          >
            <LayoutGrid className="h-4 w-4" />
          </Button>
          <Button
            variant={view === 'list' ? 'default' : 'ghost'}
            size="icon"
            onClick={() => setView('list')}
            className="rounded-l-none"
          >
            <List className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Filters row */}
      <div className="flex flex-wrap gap-3 mb-6">
        {/* Date range */}
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-muted-foreground" />
          <input
            type="month"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="text-sm border rounded px-2 py-1 bg-background"
            placeholder="From"
          />
          <span className="text-muted-foreground text-sm">to</span>
          <input
            type="month"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="text-sm border rounded px-2 py-1 bg-background"
          />
          {(dateFrom || dateTo) && (
            <Button variant="ghost" size="sm" onClick={() => { setDateFrom(''); setDateTo(''); }}>
              Clear
            </Button>
          )}
        </div>

        {/* Guest filter (disabled) */}
        <Button variant="outline" size="sm" disabled className="gap-2 opacity-50">
          <Users className="h-4 w-4" />
          Filter by guest
          <span className="text-xs bg-muted px-1.5 py-0.5 rounded">Soon</span>
        </Button>
      </div>

      {/* Results count */}
      <p className="text-sm text-muted-foreground mb-4">
        {filtered.length} episode{filtered.length !== 1 ? 's' : ''}
        {search && ` matching "${search}"`}
      </p>

      {/* Grid view */}
      {view === 'grid' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filtered.map((episode) => (
            <EpisodeCard key={episode.id} episode={episode} channelSlug={channelSlug} />
          ))}
        </div>
      )}

      {/* List view */}
      {view === 'list' && (
        <div className="space-y-2">
          {filtered.map((episode) => {
            const thumbnailUrl = episode.thumbnail_url
              || `https://img.youtube.com/vi/${episode.youtube_id}/hqdefault.jpg`;
            return (
              <Link key={episode.id} href={`/${channelSlug}/episodes/${episode.youtube_id}`}>
                <div className="flex gap-4 p-3 rounded-lg hover:bg-accent transition-colors group">
                  <div className="relative w-40 aspect-video flex-shrink-0 rounded overflow-hidden">
                    <Image
                      src={thumbnailUrl}
                      alt={episode.title}
                      fill
                      className="object-cover"
                    />
                    {episode.duration_seconds && (
                      <span className="absolute bottom-1 right-1 bg-black/80 text-white text-xs px-1.5 py-0.5 rounded">
                        {formatDuration(episode.duration_seconds)}
                      </span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium line-clamp-2 group-hover:text-primary transition-colors">
                      {episode.title}
                    </h3>
                    <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                      {episode.published_at && (
                        <span>{format(new Date(episode.published_at), 'MMM d, yyyy')}</span>
                      )}
                      {episode.duration_seconds && (
                        <span>{formatDuration(episode.duration_seconds)}</span>
                      )}
                    </div>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}

      {/* Empty state */}
      {filtered.length === 0 && (
        <div className="text-center py-12">
          <p className="text-muted-foreground">
            {search ? `No episodes matching "${search}"` : 'No episodes yet.'}
          </p>
        </div>
      )}
    </div>
  );
}
